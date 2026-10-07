from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import database as db


def _pipeline(name: str = "Standard", pipeline_id: str = "pipeline-1", is_default: bool = True):
    return {
        "id": pipeline_id,
        "name": name,
        "is_default": is_default,
        "is_archived": False,
        "stages": [{"id": "stage-1", "name": "Sourced"}, {"id": "stage-2", "name": "Hired"}],
    }


class FakeClientsCollection:
    def __init__(self, rows=None) -> None:
        self.rows = list(rows or [])
        self.inserted = []
        self.write_calls = 0

    def find_one(self, query):
        return next(
            (row for row in self.rows if all(row.get(key) == value for key, value in query.items())),
            None,
        )

    def insert_one(self, row) -> None:
        self.write_calls += 1
        self.inserted.append(row)
        self.rows.append(row)

    def update_one(self, query, update) -> None:
        self.write_calls += 1
        row = self.find_one(query)
        if row:
            row.update(update.get("$set", {}))


class ClientHiringConfigReadTests(unittest.TestCase):
    def test_legacy_client_is_normalized_without_database_writes(self) -> None:
        clients = FakeClientsCollection(
            [
                {
                    "id": 81,
                    "client_account_id": "LEGACY",
                    "name": "Legacy Client",
                    "hiring_stages": [
                        {"name": "Sourced", "order": 0},
                        {"name": "Hired", "order": 1},
                    ],
                }
            ]
        )
        with patch.object(db, "_database", return_value=SimpleNamespace(clients=clients)):
            client = db.get_client_by_id(81)

        self.assertEqual(len(client["hiring_pipelines"]), 1)
        self.assertEqual(client["hiring_pipelines"][0]["name"], "Standard")
        self.assertTrue(client["hiring_pipelines"][0]["is_default"])
        self.assertEqual(client["roles"], [])
        self.assertEqual(client["hiring_stages"], client["hiring_pipelines"][0]["stages"])
        self.assertEqual(clients.write_calls, 0)

    def test_legacy_pipeline_id_is_stable_across_reads(self) -> None:
        clients = FakeClientsCollection(
            [
                {
                    "id": 82,
                    "name": "Legacy Client",
                    "hiring_stages": ["Sourced", "Hired"],
                }
            ]
        )
        with patch.object(db, "_database", return_value=SimpleNamespace(clients=clients)):
            first = db.get_client_by_id(82)
            second = db.get_client_by_id(82)

        self.assertEqual(first["hiring_pipelines"][0]["id"], second["hiring_pipelines"][0]["id"])
        self.assertEqual(
            [stage["id"] for stage in first["hiring_pipelines"][0]["stages"]],
            [stage["id"] for stage in second["hiring_pipelines"][0]["stages"]],
        )
        self.assertEqual(clients.write_calls, 0)

    def test_client_detail_response_includes_pipeline_and_role_fields(self) -> None:
        client = {
            "id": 83,
            "name": "Client",
            "hiring_pipelines": [_pipeline()],
            "roles": [
                {
                    "id": "role-1",
                    "title": "Engineer",
                    "level": "Senior",
                    "pipeline_id": "pipeline-1",
                    "is_archived": False,
                }
            ],
        }
        empty_collection = SimpleNamespace(
            count_documents=lambda _query: 0,
            find=lambda *_args, **_kwargs: [],
        )
        with patch.object(db, "get_client_by_id", return_value=client), \
            patch.object(db, "get_projects_for_client", return_value=[]), \
            patch.object(
                db,
                "_database",
                return_value=SimpleNamespace(
                    job_descriptions=empty_collection,
                    candidates=empty_collection,
                    interviews=empty_collection,
                ),
            ):
            result = db.get_client_details(83)

        self.assertEqual(result["client"]["hiring_pipelines"][0]["id"], "pipeline-1")
        self.assertEqual(result["client"]["roles"][0]["title"], "Engineer")


class CreateClientHiringConfigTests(unittest.TestCase):
    def _create(self, payload):
        clients = FakeClientsCollection()
        database = SimpleNamespace(clients=clients)
        with patch.object(db, "_database", return_value=database), \
            patch.object(db, "_next_id", return_value=91), \
            patch.object(db, "get_client_by_account_id", return_value=None), \
            patch.object(db, "_default_project_payload_for_client", return_value={}), \
            patch.object(db, "create_project"):
            client_id = db.create_client(
                {
                    "name": "New Client",
                    "client_account_id": "NEWCLIENT",
                    **payload,
                }
            )
        return client_id, clients.inserted[0]

    def test_create_accepts_multiple_pipelines_and_generates_missing_ids(self) -> None:
        client_id, stored = self._create(
            {
                "hiring_pipelines": [
                    {
                        "name": "Engineering",
                        "is_default": True,
                        "stages": [{"name": "Sourced"}, {"name": "Hired"}],
                    },
                    {
                        "id": "leadership-pipeline",
                        "name": "Leadership",
                        "is_default": False,
                        "stages": [{"name": "Screening"}, {"name": "Offer"}],
                    },
                ],
                "roles": [
                    {
                        "title": "Platform Engineer",
                        "level": "Senior",
                        "pipeline_id": "leadership-pipeline",
                    }
                ],
            }
        )

        self.assertEqual(client_id, 91)
        self.assertEqual(stored["hiring_pipelines"][0]["name"], "Engineering")
        self.assertTrue(stored["hiring_pipelines"][0]["id"])
        self.assertTrue(
            all(
                stage["id"]
                for pipeline in stored["hiring_pipelines"]
                for stage in pipeline["stages"]
            )
        )
        self.assertEqual(stored["hiring_pipelines"][0]["stages"][0]["order"], 0)
        self.assertEqual(stored["roles"][0]["pipeline_id"], "leadership-pipeline")
        self.assertTrue(stored["roles"][0]["id"])
        self.assertEqual(stored["hiring_stages"], stored["hiring_pipelines"][0]["stages"])

    def test_create_accepts_legacy_stage_list_and_mirrors_default_pipeline(self) -> None:
        _, stored = self._create({"hiring_stages": ["Applied", "Hired"]})

        self.assertEqual(stored["hiring_pipelines"][0]["name"], "Standard")
        self.assertTrue(stored["hiring_pipelines"][0]["id"])
        self.assertTrue(stored["hiring_pipelines"][0]["is_default"])
        self.assertEqual(stored["hiring_stages"], stored["hiring_pipelines"][0]["stages"])


class ValidateClientHiringConfigTests(unittest.TestCase):
    def test_generates_missing_pipeline_stage_and_role_ids(self) -> None:
        config = db.validate_client_hiring_config(
            {
                "hiring_pipelines": [
                    {
                        "name": "Standard",
                        "is_default": True,
                        "stages": [{"name": "Sourced"}, {"name": "Hired"}],
                    }
                ]
            }
        )
        # A role must refer to the generated pipeline ID, so add it in a
        # second call using the assigned ID.
        config = db.validate_client_hiring_config(
            {
                "hiring_pipelines": config["hiring_pipelines"],
                "roles": [
                    {
                        "title": "Engineer",
                        "level": "Mid",
                        "pipeline_id": config["hiring_pipelines"][0]["id"],
                    }
                ],
            }
        )

        self.assertTrue(config["hiring_pipelines"][0]["id"])
        self.assertTrue(all(stage["id"] for stage in config["hiring_pipelines"][0]["stages"]))
        self.assertTrue(config["roles"][0]["id"])

    def test_rejects_invalid_pipeline_and_role_configurations(self) -> None:
        valid = _pipeline()
        invalid_cases = [
            ([{**valid, "is_default": False}], [], "(?i)exactly one"),
            ([valid, {**_pipeline("Other", "pipeline-2"), "is_default": True}], [], "(?i)exactly one"),
            ([{**valid, "stages": [{"name": "Only stage"}]}], [], "at least two"),
            ([{**valid, "name": "  "}], [], "names cannot be empty"),
            ([valid, _pipeline("standard", "pipeline-2", False)], [], "names must be unique"),
            ([{**valid, "stages": [{"name": " "}, {"name": "Hired"}]}], [], "stage names cannot be empty"),
            ([{**valid, "stages": [{"name": "Sourced"}, {"name": "sourced"}]}], [], "stage names must be unique"),
            ([{**valid, "stages": [{"name": "x" * 40}, {"name": "Hired"}]}], [], "under 40"),
            (
                [valid],
                [{"title": "Engineer", "level": "Intern", "pipeline_id": "pipeline-1"}],
                "Role level must be",
            ),
            (
                [valid],
                [{"title": "Engineer", "level": "Mid", "pipeline_id": "missing"}],
                "must reference a pipeline",
            ),
        ]
        for pipelines, roles, message in invalid_cases:
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                db.validate_client_hiring_config(
                    {"hiring_pipelines": pipelines, "roles": roles}
                )


class ClientHiringConfigMutationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client_doc = {
            "id": 101,
            "client_account_id": "CLIENT101",
            "name": "Client 101",
            "hiring_pipelines": [
                {
                    "id": "pipeline-default",
                    "name": "Standard",
                    "is_default": True,
                    "is_archived": False,
                    "stages": [
                        {"id": "stage-a", "name": "Source", "order": 0},
                        {"id": "stage-b", "name": "Screen", "order": 1},
                        {"id": "stage-c", "name": "Offer", "order": 2},
                    ],
                },
                {
                    "id": "pipeline-other",
                    "name": "Leadership",
                    "is_default": False,
                    "is_archived": False,
                    "stages": [
                        {"id": "stage-d", "name": "Review", "order": 0},
                        {"id": "stage-e", "name": "Decision", "order": 1},
                    ],
                },
            ],
            "roles": [
                {
                    "id": "role-active",
                    "title": "Engineer",
                    "level": "Senior",
                    "pipeline_id": "pipeline-other",
                    "is_archived": False,
                },
                {
                    "id": "role-archived",
                    "title": "Old Engineer",
                    "level": "Mid",
                    "pipeline_id": "pipeline-other",
                    "is_archived": True,
                },
            ],
            "hiring_stages": [],
        }
        self.clients = FakeClientsCollection([self.client_doc])
        self.database = SimpleNamespace(clients=self.clients)
        self.database_patch = patch.object(db, "_database", return_value=self.database)
        self.database_patch.start()
        self.addCleanup(self.database_patch.stop)

    def test_stage_ids_stay_stable_across_rename_and_reorder(self) -> None:
        updated = db.update_client_pipeline(
            101,
            "pipeline-default",
            {
                "stages": [
                    {"id": "stage-c", "name": "Offer"},
                    {"id": "stage-a", "name": "Prospecting"},
                    {"name": "Screen"},
                ]
            },
        )

        stages = updated["hiring_pipelines"][0]["stages"]
        self.assertEqual(
            [(stage["id"], stage["name"], stage["order"]) for stage in stages],
            [
                ("stage-c", "Offer", 0),
                ("stage-a", "Prospecting", 1),
                ("stage-b", "Screen", 2),
            ],
        )

    def test_stage_ids_match_by_name_then_position_when_ids_are_omitted(self) -> None:
        updated = db.update_client_pipeline(
            101,
            "pipeline-default",
            {
                "stages": [
                    {"name": "New first stage"},
                    {"name": "Offer"},
                    {"name": "Screen"},
                ]
            },
        )

        stages = updated["hiring_pipelines"][0]["stages"]
        self.assertEqual(
            [(stage["id"], stage["name"]) for stage in stages],
            [
                ("stage-a", "New first stage"),
                ("stage-c", "Offer"),
                ("stage-b", "Screen"),
            ],
        )

    def test_new_default_clears_old_default_and_updates_stage_mirror(self) -> None:
        updated = db.update_client_pipeline(
            101,
            "pipeline-other",
            {"is_default": True, "stages": ["Review", "Decision"]},
        )

        defaults = [pipeline for pipeline in updated["hiring_pipelines"] if pipeline["is_default"]]
        self.assertEqual([pipeline["id"] for pipeline in defaults], ["pipeline-other"])
        self.assertEqual(updated["hiring_stages"], defaults[0]["stages"])
        self.assertEqual(self.client_doc["hiring_stages"], defaults[0]["stages"])

    def test_adding_default_pipeline_clears_previous_default(self) -> None:
        updated = db.add_client_pipeline(
            101,
            {
                "name": "Operations",
                "is_default": True,
                "stages": ["Intake", "Complete"],
            },
        )

        defaults = [pipeline for pipeline in updated["hiring_pipelines"] if pipeline["is_default"]]
        self.assertEqual(len(defaults), 1)
        self.assertEqual(defaults[0]["name"], "Operations")
        self.assertEqual(updated["hiring_stages"], defaults[0]["stages"])

    def test_default_pipeline_cannot_be_archived(self) -> None:
        writes_before = self.clients.write_calls
        with self.assertRaisesRegex(ValueError, "default hiring pipeline cannot be archived"):
            db.update_client_pipeline(101, "pipeline-default", {"is_archived": True})
        self.assertEqual(self.clients.write_calls, writes_before)

    def test_archiving_pipeline_with_active_roles_requires_move_target(self) -> None:
        with self.assertRaisesRegex(ValueError, "Move active roles"):
            db.update_client_pipeline(101, "pipeline-other", {"is_archived": True})

        updated = db.update_client_pipeline(
            101,
            "pipeline-other",
            {
                "is_archived": True,
                "move_roles_to_pipeline_id": "pipeline-default",
            },
        )
        pipeline = next(row for row in updated["hiring_pipelines"] if row["id"] == "pipeline-other")
        self.assertTrue(pipeline["is_archived"])
        active_role = next(role for role in updated["roles"] if role["id"] == "role-active")
        archived_role = next(role for role in updated["roles"] if role["id"] == "role-archived")
        self.assertEqual(active_role["pipeline_id"], "pipeline-default")
        self.assertEqual(archived_role["pipeline_id"], "pipeline-other")

    def test_pipeline_archive_cannot_move_roles_to_archived_pipeline(self) -> None:
        with self.assertRaisesRegex(ValueError, "another active pipeline"):
            db.update_client_pipeline(
                101,
                "pipeline-other",
                {
                    "is_archived": True,
                    "move_roles_to_pipeline_id": "pipeline-other",
                },
            )

    def test_role_create_edit_and_archive_use_config_validation(self) -> None:
        created = db.add_client_role(
            101,
            {
                "title": "Recruiting Lead",
                "level": "Lead",
                "pipeline_id": "pipeline-other",
            },
        )
        role = next(role for role in created["roles"] if role["title"] == "Recruiting Lead")
        self.assertTrue(role["id"])

        updated = db.update_client_role(
            101,
            role["id"],
            {"title": "Talent Lead", "level": "Senior", "pipeline_id": "pipeline-default"},
        )
        role_id = role["id"]
        role = next(updated_role for updated_role in updated["roles"] if updated_role["id"] == role_id)
        self.assertEqual(role["title"], "Talent Lead")
        self.assertEqual(role["pipeline_id"], "pipeline-default")

        archived = db.update_client_role(101, role_id, {"is_archived": True})
        role = next(updated_role for updated_role in archived["roles"] if updated_role["id"] == role_id)
        self.assertTrue(role["is_archived"])

    def test_legacy_first_edit_persists_standard_pipeline_and_change(self) -> None:
        legacy = {
            "id": 102,
            "name": "Legacy",
            "hiring_stages": [{"name": "Applied", "order": 0}, {"name": "Hired", "order": 1}],
        }
        clients = FakeClientsCollection([legacy])
        with patch.object(db, "_database", return_value=SimpleNamespace(clients=clients)):
            normalized_before = db.get_client_by_id(102)
            updated = db.update_client_pipeline(
                102,
                normalized_before["hiring_pipelines"][0]["id"],
                {"name": "Legacy Standard"},
            )

        self.assertEqual(updated["hiring_pipelines"][0]["name"], "Legacy Standard")
        self.assertTrue(clients.rows[0]["hiring_pipelines"][0]["is_default"])
        self.assertEqual(clients.rows[0]["hiring_stages"], clients.rows[0]["hiring_pipelines"][0]["stages"])

    def test_missing_client_pipeline_and_role_return_none(self) -> None:
        self.assertIsNone(db.add_client_pipeline(999, {"name": "Another", "stages": ["A", "B"]}))
        self.assertIsNone(db.update_client_pipeline(101, "missing", {}))
        self.assertIsNone(db.add_client_role(999, {}))
        self.assertIsNone(db.update_client_role(101, "missing", {}))


class ClientHiringConfigRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        from flask import Flask
        from routes.client_routes import client_bp

        self.app = Flask(__name__)
        self.app.secret_key = "test"
        self.app.register_blueprint(client_bp)
        self.client = self.app.test_client()

    def test_all_new_routes_require_login(self) -> None:
        responses = [
            self.client.post("/api/clients/1/pipelines", json={}),
            self.client.put("/api/clients/1/pipelines/p1", json={}),
            self.client.post("/api/clients/1/roles", json={}),
            self.client.put("/api/clients/1/roles/r1", json={}),
        ]
        self.assertEqual([response.status_code for response in responses], [401, 401, 401, 401])

    def test_routes_return_updated_client_and_expected_error_statuses(self) -> None:
        from routes import client_routes

        with self.client.session_transaction() as session:
            session["user_id"] = 1
        with patch.object(client_routes.db, "add_client_pipeline", return_value={"id": 1}), \
            patch.object(client_routes.db, "update_client_pipeline", return_value={"id": 1}), \
            patch.object(client_routes.db, "add_client_role", return_value={"id": 1}), \
            patch.object(client_routes.db, "update_client_role", return_value={"id": 1}):
            responses = [
                self.client.post("/api/clients/1/pipelines", json={"name": "Standard"}),
                self.client.put("/api/clients/1/pipelines/p1", json={"name": "Renamed"}),
                self.client.post("/api/clients/1/roles", json={"title": "Engineer"}),
                self.client.put("/api/clients/1/roles/r1", json={"title": "Engineer"}),
            ]

        self.assertTrue(all(response.status_code == 200 for response in responses))
        self.assertTrue(all(response.json["success"] for response in responses))
        self.assertTrue(all(response.json["client"]["id"] == 1 for response in responses))

        with patch.object(client_routes.db, "add_client_pipeline", side_effect=ValueError("Bad config")):
            invalid = self.client.post("/api/clients/1/pipelines", json={"name": "Bad"})
        with patch.object(client_routes.db, "update_client_role", return_value=None):
            missing = self.client.put("/api/clients/1/roles/missing", json={"title": "No role"})
        with patch.object(client_routes.db, "add_client_pipeline", return_value=None):
            missing_client = self.client.post("/api/clients/999/pipelines", json={"name": "New"})
        with patch.object(client_routes.db, "update_client_pipeline", return_value=None):
            missing_pipeline = self.client.put("/api/clients/1/pipelines/missing", json={"name": "No pipeline"})
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(invalid.json["error"], "Bad config")
        self.assertEqual(
            [missing.status_code, missing_client.status_code, missing_pipeline.status_code],
            [404, 404, 404],
        )


if __name__ == "__main__":
    unittest.main()
