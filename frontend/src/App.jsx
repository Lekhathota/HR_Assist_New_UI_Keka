import React, { lazy, Suspense } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate, useLocation } from 'react-router-dom';

import Login from './pages/Login.jsx';
import { getToken } from './api.js';
import { getCurrentRole, roleCanAccess } from './roleAccess.js';
import { ConfirmProvider, ToastHost } from './components/EnterpriseFeedback.jsx';
import { CommandPalette, FrontendPolishProvider } from './components/FrontendPolish.jsx';
import { HireRedirect } from './components/HireNav.jsx';
import './styles/style.css';

const Welcome = lazy(() => import('./pages/Welcome.jsx'));
const JdList = lazy(() => import('./pages/JdList.jsx'));
const JdCreate = lazy(() => import('./pages/JdCreate.jsx'));
const JdDetails = lazy(() => import('./pages/JdDetails.jsx'));
const Comparison = lazy(() => import('./pages/Comparison.jsx'));
const Candidates = lazy(() => import('./pages/Candidates.jsx'));
const CandidateProfile = lazy(() => import('./pages/CandidateProfile.jsx'));
const Clients = lazy(() => import('./pages/Clients.jsx'));
const ClientProject = lazy(() => import('./pages/ClientProject.jsx'));
const Vendors = lazy(() => import('./pages/Vendors.jsx'));
const UserManagement = lazy(() => import('./pages/UserManagement.jsx'));
const HiringPipeline = lazy(() => import('./pages/Interviews.jsx'));
const Reports = lazy(() => import('./pages/Reports.jsx'));
const Profile = lazy(() => import('./pages/Profile.jsx'));
const CandidateAssessment = lazy(() => import('./pages/CandidateAssessment.jsx'));
const AssessmentBuilder = lazy(() => import('./pages/AssessmentBuilder.jsx'));


function ProtectedRoute({ children }) {
  const location = useLocation();
  if (!getToken()) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }
  if (!roleCanAccess(getCurrentRole(), location.pathname)) {
    return <Navigate to="/welcome" replace />;
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
          <Suspense fallback={<div role="status" style={{ padding: 24 }}>Loading page...</div>}>
          <Routes>

        <Route path="/" element={<Navigate to={getToken() ? '/welcome' : '/login'} replace />} />

        <Route path="/login" element={<Login />} />
        <Route path="/assessment/:token" element={<CandidateAssessment />} />
        <Route path="/welcome" element={<ProtectedRoute><Welcome /></ProtectedRoute>} />
        <Route path="/dashboard" element={<ProtectedRoute><Navigate to="/welcome" replace /></ProtectedRoute>} />

        <Route path="/hire" element={<ProtectedRoute><HireRedirect /></ProtectedRoute>} />
        <Route path="/jobs" element={<ProtectedRoute><JdList /></ProtectedRoute>} />
        <Route path="/jobs/create" element={<ProtectedRoute><JdCreate /></ProtectedRoute>} />
        <Route path="/job-details.html" element={<ProtectedRoute><JdDetails /></ProtectedRoute>} />
        <Route path="/jobs/:jdId" element={<ProtectedRoute><JdDetails /></ProtectedRoute>} />
        <Route path="/jobs/:jdId/assessment/:assessmentId" element={<ProtectedRoute><AssessmentBuilder /></ProtectedRoute>} />
        <Route path="/hiring-pipeline/assessment/:assessmentId" element={<ProtectedRoute><AssessmentBuilder /></ProtectedRoute>} />

        <Route path="/analyze" element={<ProtectedRoute><Comparison /></ProtectedRoute>} />
        <Route path="/talent" element={<ProtectedRoute><Candidates /></ProtectedRoute>} />
        <Route path="/talent/:candidateId" element={<ProtectedRoute><CandidateProfile /></ProtectedRoute>} />
        <Route path="/clients" element={<ProtectedRoute><Clients /></ProtectedRoute>} />
        <Route path="/clients/create" element={<ProtectedRoute><Clients createPage /></ProtectedRoute>} />
        <Route path="/clients/:clientId/projects/:projectId" element={<ProtectedRoute><ClientProject /></ProtectedRoute>} />
        <Route path="/vendors" element={<ProtectedRoute><Vendors /></ProtectedRoute>} />
        <Route path="/admin/users" element={<ProtectedRoute><UserManagement /></ProtectedRoute>} />
        <Route path="/hiring-pipeline" element={<ProtectedRoute><HiringPipeline /></ProtectedRoute>} />
        <Route path="/interviews" element={<Navigate to="/hiring-pipeline" replace />} />

        <Route path="/insights" element={<ProtectedRoute><Reports /></ProtectedRoute>} />
        <Route path="/profile" element={<ProtectedRoute><Profile /></ProtectedRoute>} />

        <Route path="*" element={<Navigate to="/login" replace />} />

          </Routes>
          </Suspense>
        </ConfirmProvider>
      </FrontendPolishProvider>
    </Router>
  );
}

export default App;
