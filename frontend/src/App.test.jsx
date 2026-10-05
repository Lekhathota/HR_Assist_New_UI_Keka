import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.jsx';
jest.mock('./api.js', () => ({ getToken: () => globalThis.localStorage.getItem('session_token') }));
jest.mock('./components/EnterpriseFeedback.jsx', () => ({ ConfirmProvider: ({ children }) => children, ToastHost: () => null }));
jest.mock('./components/FrontendPolish.jsx', () => ({ FrontendPolishProvider: ({ children }) => children, CommandPalette: () => null }));
jest.mock('./pages/Login.jsx', () => () => <p>Login fixture</p>);
jest.mock('./pages/Welcome.jsx', () => () => <p>Home fixture</p>);
jest.mock('./pages/JdList.jsx', () => () => <p>Jobs fixture</p>);
jest.mock('./pages/JdCreate.jsx', () => () => <p>Create job fixture</p>);
jest.mock('./pages/JdDetails.jsx', () => () => <p>Job detail fixture</p>);
jest.mock('./pages/Comparison.jsx', () => () => <p>Analyze fixture</p>);
jest.mock('./pages/Candidates.jsx', () => () => <p>Talent fixture</p>);
jest.mock('./pages/CandidateProfile.jsx', () => () => <p>Candidate fixture</p>);
jest.mock('./pages/Clients.jsx', () => () => <p>Clients fixture</p>);
jest.mock('./pages/ClientProject.jsx', () => () => <p>Project fixture</p>);
jest.mock('./pages/Vendors.jsx', () => () => <p>Vendors fixture</p>);
jest.mock('./pages/UserManagement.jsx', () => () => <p>Users fixture</p>);
jest.mock('./pages/Interviews.jsx', () => () => <p>Pipeline fixture</p>);
jest.mock('./pages/Reports.jsx', () => () => <p>Reports fixture</p>);
jest.mock('./pages/Profile.jsx', () => () => <p>Profile fixture</p>);
jest.mock('./pages/CandidateAssessment.jsx', () => () => <p>Public assessment fixture</p>);
jest.mock('./pages/AssessmentBuilder.jsx', () => () => <p>Builder fixture</p>);
let root, container;
beforeEach(() => { globalThis.IS_REACT_ACT_ENVIRONMENT = true; localStorage.clear(); localStorage.setItem('session_token', 'fixture'); localStorage.setItem('recruitment_assist_user', JSON.stringify({ role: 'admin' })); container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container); });
afterEach(() => { act(() => root.unmount()); container.remove(); });
function visit(path) { window.history.replaceState({}, '', path); act(() => root.render(<App />)); }
test('old Dashboard bookmarks resolve to Home', () => { visit('/dashboard'); expect(window.location.pathname).toBe('/welcome'); expect(container.textContent).toContain('Home fixture'); });
test('Home still requires login', () => { localStorage.removeItem('session_token'); visit('/welcome'); expect(window.location.pathname).toBe('/login'); });
test('Reports access remains role-restricted', () => { localStorage.setItem('recruitment_assist_user', JSON.stringify({ role: 'recruiter' })); visit('/insights'); expect(window.location.pathname).toBe('/welcome'); });
test.each([
  ['/jobs', 'Jobs'], ['/jobs/14', 'Job detail'], ['/jobs/create', 'Create job'], ['/analyze', 'Analyze'],
  ['/talent', 'Talent'], ['/talent/2', 'Candidate'], ['/clients', 'Clients'], ['/clients/3/projects/4', 'Project'],
  ['/vendors', 'Vendors'], ['/admin/users', 'Users'], ['/hiring-pipeline', 'Pipeline'], ['/insights', 'Reports'],
  ['/profile', 'Profile'], ['/assessment/token', 'Public assessment'], ['/jobs/1/assessment/2', 'Builder'],
])('existing destination %s retains its page', (path, expected) => { visit(path); expect(container.textContent).toContain(`${expected} fixture`); });
