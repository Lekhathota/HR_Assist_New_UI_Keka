import React, { useEffect, useState, useRef } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import Layout from '../components/Layout.jsx';
import { toast } from '../components/EnterpriseFeedback.jsx';
import { apiGet, apiPostForm } from '../api.js';
import '../styles/profile_extra.css';
import '../styles/jd_create.css';

function JdCreate() {
  const [fileName, setFileName]   = useState('');
  const [isDragOver, setIsDragOver] = useState(false);
  const [loading, setLoading]     = useState(false);
  const [error, setError]         = useState('');
  const [clients, setClients]     = useState([]);
  const [clientId, setClientId]   = useState('');
  const [requiredCount, setRequiredCount] = useState('');
  const inputRef = useRef(null);
  const navigate = useNavigate();

  useEffect(() => {
    apiGet('/api/clients')
      .then((data) => {
        const rows = Array.isArray(data.clients) ? data.clients : [];
        setClients(rows);
        setClientId(String(rows[0]?.id || ''));
      })
      .catch(() => {
        setClients([]);
      });
  }, []);

  const handleFileChange = (file) => { if (file) setFileName(file.name); };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragOver(false);
    if (e.dataTransfer.files.length) {
      inputRef.current.files = e.dataTransfer.files;
      handleFileChange(e.dataTransfer.files[0]);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    const formData = new FormData(e.target);
    if (!formData.get('client_id')) {
      setLoading(false);
      setError('Select a client before uploading a job description.');
      return;
    }
    if (!Number.isInteger(Number(formData.get('required_candidate_count'))) || Number(formData.get('required_candidate_count')) <= 0) {
      setLoading(false);
      setError('Enter a required candidate count greater than zero.');
      return;
    }
    try {
      const { ok, data } = await apiPostForm('/api/jds/create', formData);
      if (ok && data.success) {
        toast({ type: 'success', message: 'Job description created.' });
        navigate('/jobs');
      } else {
        const message = data.error || 'Upload failed';
        setError(message);
        toast({ type: 'error', message });
      }
    } catch {
      const message = 'Upload failed. Please try again.';
      setError(message);
      toast({ type: 'error', message });
    } finally {
      setLoading(false);
    }
  };

  return (
    <Layout>
      <div className="jd-create-container">
        <div className="jd-create-header">
          <h1><i className="fas fa-plus-circle"></i> Create JD</h1>
          <p>Upload and extract job requirements</p>
        </div>

        <div className="form-container">
          <form onSubmit={handleSubmit} encType="multipart/form-data">
            <div className="form-group">
              <label htmlFor="client_id" className="jd-create-label-color">
                <i className="fas fa-building"></i> Client Account
              </label>
              <select
                id="client_id"
                name="client_id"
                className="jd-create-select"
                value={clientId}
                required
                onChange={(event) => setClientId(event.target.value)}
              >
                <option value="">Select client account</option>
                {clients.map((client) => (
                  <option key={client.id} value={client.id}>
                    {client.name} ({client.client_account_id})
                  </option>
                ))}
              </select>
              <div className="file-info">
                <i className="fas fa-link"></i> This job and its screened candidates will be linked to the selected client.
              </div>
            </div>

            <div className="form-group">
              <label htmlFor="required_candidate_count" className="jd-create-label-color">
                <i className="fas fa-users"></i> Required Candidate Count
              </label>
              <input
                id="required_candidate_count"
                name="required_candidate_count"
                type="number"
                min="1"
                step="1"
                value={requiredCount}
                required
                onChange={(event) => setRequiredCount(event.target.value)}
                placeholder="How many candidates are needed?"
              />
              <div className="file-info">The workflow will fill this requirement from matching internal bench candidates first.</div>
            </div>

            <div className="form-group">
              <label htmlFor="jd_file" className="jd-create-label-color">
                <i className="fas fa-upload"></i> Upload Job Description
              </label>
              <div
                className={`drop-zone${isDragOver ? ' drop-zone--over' : ''}`}
                onClick={() => inputRef.current.click()}
                onDragOver={(e) => { e.preventDefault(); setIsDragOver(true); }}
                onDragLeave={() => setIsDragOver(false)}
                onDrop={handleDrop}
              >
                {fileName
                  ? <div className="drop-zone__thumb"><i className="fas fa-file-alt jd-create-file-icon"></i>{fileName}</div>
                  : <span className="drop-zone__prompt">Drop file here or click to upload</span>
                }
                <input type="file" name="file" id="jd_file" ref={inputRef}
                  className="drop-zone__input" accept=".pdf,.docx" required
                  onChange={(e) => handleFileChange(e.target.files[0])} />
              </div>
              <div className="file-info">
                <i className="fas fa-info-circle"></i> Supported formats: <strong>PDF, DOCX</strong>
              </div>
            </div>

            {error && <div className="jd-create-error">{error}</div>}

            <button type="submit" disabled={loading}>
              {loading
                ? <><i className="fas fa-spinner fa-spin"></i> Processing...</>
                : <><i className="fas fa-magic"></i> Upload &amp; Extract</>}
            </button>
          </form>
        </div>

        <Link to="/jobs" className="back-link"><i className="fas fa-arrow-left"></i> Back to JDs</Link>
      </div>
    </Layout>
  );
}

export default JdCreate;
