import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate, useLocation } from 'react-router-dom';

import Login from './pages/Login.jsx';
import Dashboard from './pages/Dashboard.jsx';
import Welcome from './pages/Welcome.jsx';
import JdList from './pages/JdList.jsx';
import JdCreate from './pages/JdCreate.jsx';
import JdDetails from './pages/JdDetails.jsx';
import Comparison from './pages/Comparison.jsx';
import Candidates from './pages/Candidates.jsx';
import CandidateProfile from './pages/CandidateProfile.jsx';
import Clients from './pages/Clients.jsx';
import ClientProject from './pages/ClientProject.jsx';
import Vendors from './pages/Vendors.jsx';
import WorkflowAdmin from './pages/WorkflowAdmin.jsx';
import HiringPipeline from './pages/Interviews.jsx';
import Reports from './pages/Reports.jsx';
import Profile from './pages/Profile.jsx';
import CandidateAssessment from './pages/CandidateAssessment.jsx';
import AssessmentBuilder from './pages/AssessmentBuilder.jsx';
import { getToken } from './api.js';
import { ConfirmProvider, ToastHost } from './components/EnterpriseFeedback.jsx';
import { CommandPalette, FrontendPolishProvider } from './components/FrontendPolish.jsx';

import './styles/style.css';

function ProtectedRoute({ children }) {
  const location = useLocation();
  if (!getToken()) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  return children;
}

function App() {
  return (
    <Router>
      <FrontendPolishProvider>
        <ConfirmProvider>
          <ToastHost />
          <CommandPalette />
          <Routes>

        <Route path="/" element={<Navigate to="/login" replace />} />

        <Route path="/login" element={<Login />} />
        <Route path="/assessment/:token" element={<CandidateAssessment />} />
        <Route path="/welcome" element={<ProtectedRoute><Welcome /></ProtectedRoute>} />
        <Route path="/dashboard" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />

        <Route path="/jobs" element={<ProtectedRoute><JdList /></ProtectedRoute>} />
        <Route path="/jobs/create" element={<ProtectedRoute><JdCreate /></ProtectedRoute>} />
        <Route path="/jobs/:jdId" element={<ProtectedRoute><JdDetails /></ProtectedRoute>} />
        <Route path="/jobs/:jdId/assessment/:assessmentId" element={<ProtectedRoute><AssessmentBuilder /></ProtectedRoute>} />
        <Route path="/hiring-pipeline/assessment/:assessmentId" element={<ProtectedRoute><AssessmentBuilder /></ProtectedRoute>} />

        <Route path="/analyze" element={<ProtectedRoute><Comparison /></ProtectedRoute>} />
        <Route path="/talent" element={<ProtectedRoute><Candidates /></ProtectedRoute>} />
        <Route path="/talent/:candidateId" element={<ProtectedRoute><CandidateProfile /></ProtectedRoute>} />
        <Route path="/clients" element={<ProtectedRoute><Clients /></ProtectedRoute>} />
        <Route path="/clients/:clientId/projects/:projectId" element={<ProtectedRoute><ClientProject /></ProtectedRoute>} />
        <Route path="/vendors" element={<ProtectedRoute><Vendors /></ProtectedRoute>} />
        <Route path="/admin/workflow" element={<ProtectedRoute><WorkflowAdmin /></ProtectedRoute>} />
        <Route path="/hiring-pipeline" element={<ProtectedRoute><HiringPipeline /></ProtectedRoute>} />
        <Route path="/interviews" element={<Navigate to="/hiring-pipeline" replace />} />

        <Route path="/insights" element={<ProtectedRoute><Reports /></ProtectedRoute>} />
        <Route path="/profile" element={<ProtectedRoute><Profile /></ProtectedRoute>} />

        <Route path="*" element={<Navigate to="/login" replace />} />

          </Routes>
        </ConfirmProvider>
      </FrontendPolishProvider>
    </Router>
  );
}

export default App;
