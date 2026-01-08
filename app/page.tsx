"use client";

import { useState, useRef, useEffect } from "react";

interface Job {
  id: string;
  filename: string;
  title: string | null;
  status: string;
  progress_current: number;
  progress_total: number;
  current_pass: string | null;
  latex: string | null;
  error: string | null;
  created_at: number;
  started_at: number | null;
  completed_at: number | null;
}

export default function Home() {
  const [files, setFiles] = useState<File[]>([]);
  const [converting, setConverting] = useState(false);
  const [result, setResult] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [apiStatus, setApiStatus] = useState<'checking' | 'online' | 'offline'>('checking');
  const [jobs, setJobs] = useState<Job[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

  // Check API status on mount
  useEffect(() => {
    const checkApi = async () => {
      try {
        const response = await fetch(`${apiUrl}/health`, { method: 'GET' });
        setApiStatus(response.ok ? 'online' : 'offline');
      } catch {
        setApiStatus('offline');
      }
    };
    checkApi();
    const interval = setInterval(checkApi, 10000); // Check every 10s
    return () => clearInterval(interval);
  }, [apiUrl]);

  // Poll jobs every 2 seconds
  useEffect(() => {
    const fetchJobs = async () => {
      try {
        const response = await fetch(`${apiUrl}/jobs?limit=50`);
        if (response.ok) {
          const data = await response.json();
          setJobs(data.jobs || []);
        }
      } catch (err) {
        console.error('Failed to fetch jobs:', err);
      }
    };

    fetchJobs();
    const interval = setInterval(fetchJobs, 2000); // Poll every 2 seconds
    return () => clearInterval(interval);
  }, [apiUrl]);

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      setFiles(Array.from(e.target.files));
      setResult(null);
      setError(null);
    }
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    if (e.dataTransfer.files) {
      setFiles(Array.from(e.dataTransfer.files));
      setResult(null);
      setError(null);
    }
  };

  const handleConvert = async () => {
    if (files.length === 0) return;

    setConverting(true);
    setError(null);
    setResult(null);

    const file = files[0]; // For now, only convert first file

    try:
      // Read file as base64
      const base64 = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = (e) => resolve(e.target?.result as string);
        reader.onerror = () => reject(new Error('Failed to read file'));
        reader.readAsDataURL(file);
      });

      const base64Data = base64.split(',')[1]; // Remove data:application/pdf;base64,

      // Submit job to queue
      const response = await fetch(`${apiUrl}/jobs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          pdf_base64: base64Data,
          filename: file.name,
          title: null,
          enable_compile_check: false,
        }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
        throw new Error(errorData.detail || `HTTP ${response.status}`);
      }

      const data = await response.json();
      console.log(`Job submitted: ${data.job_id}`);

      // Clear file selection
      setFiles([]);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to submit job');
    } finally {
      setConverting(false);
    }
  };

  const handleCancelJob = async (jobId: string) => {
    try {
      const response = await fetch(`${apiUrl}/jobs/${jobId}/cancel`, {
        method: 'POST',
      });
      if (!response.ok) {
        throw new Error('Failed to cancel job');
      }
    } catch (err) {
      console.error('Failed to cancel job:', err);
    }
  };

  const handleDeleteJob = async (jobId: string) => {
    try {
      const response = await fetch(`${apiUrl}/jobs/${jobId}`, {
        method: 'DELETE',
      });
      if (!response.ok) {
        throw new Error('Failed to delete job');
      }
    } catch (err) {
      console.error('Failed to delete job:', err);
    }
  };

  const handleDownload = (job: Job) => {
    if (!job.latex) return;
    const blob = new Blob([job.latex], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${job.title || 'output'}.tex`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleCopy = async (latex: string) => {
    await navigator.clipboard.writeText(latex);
  };

  const getStatusBadge = (status: string) => {
    const styles: Record<string, string> = {
      queued: 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300',
      running: 'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300',
      completed: 'bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300',
      failed: 'bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300',
      cancelled: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900 dark:text-yellow-300',
    };
    return (
      <span className={`px-2 py-1 rounded text-xs font-semibold ${styles[status] || styles.queued}`}>
        {status.toUpperCase()}
      </span>
    );
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 dark:from-gray-900 dark:to-gray-800 p-8">
      <div className="max-w-4xl mx-auto">
        {/* API Status Banner */}
        {apiStatus === 'offline' && (
          <div className="mb-6 bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg p-4">
            <div className="flex items-start gap-3">
              <span className="text-2xl">WARNING</span>
              <div className="flex-1">
                <p className="font-semibold text-yellow-800 dark:text-yellow-200 mb-1">
                  API Server Offline
                </p>
                <p className="text-sm text-yellow-700 dark:text-yellow-300 mb-2">
                  The Python API server is not running. Start it with:
                </p>
                <pre className="bg-yellow-100 dark:bg-yellow-900/40 text-yellow-900 dark:text-yellow-100 px-3 py-2 rounded text-xs font-mono">
                  cd math-ocr-app{'\n'}./start.sh
                </pre>
              </div>
            </div>
          </div>
        )}
        {apiStatus === 'online' && (
          <div className="mb-6 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg p-3">
            <div className="flex items-center gap-2">
              <span className="text-green-600 dark:text-green-400">CHECK</span>
              <p className="text-sm text-green-700 dark:text-green-300 font-medium">
                API Server Online
              </p>
            </div>
          </div>
        )}

        <h1 className="text-4xl font-bold text-gray-900 dark:text-white mb-2">
          Math OCR
        </h1>
        <p className="text-gray-600 dark:text-gray-300 mb-8">
          Convert handwritten math notes to LaTeX using Gemini 3 Flash
        </p>

        {/* Upload Zone */}
        <div
          className="border-2 border-dashed border-gray-300 dark:border-gray-600 rounded-lg p-12 text-center bg-white dark:bg-gray-800 hover:border-blue-500 dark:hover:border-blue-400 transition-colors cursor-pointer"
          onDrop={handleDrop}
          onDragOver={(e) => e.preventDefault()}
          onClick={() => fileInputRef.current?.click()}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf"
            multiple
            onChange={handleFileSelect}
            className="hidden"
          />
          <div className="text-6xl mb-4">FILE</div>
          <p className="text-lg text-gray-700 dark:text-gray-200 mb-2">
            Drop PDF files here or click to browse
          </p>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Supports single or multiple PDF files
          </p>
        </div>

        {/* File List */}
        {files.length > 0 && (
          <div className="mt-6 bg-white dark:bg-gray-800 rounded-lg p-4">
            <h3 className="font-semibold text-gray-900 dark:text-white mb-3">Selected Files:</h3>
            <ul className="space-y-2">
              {files.map((file, i) => (
                <li key={i} className="flex items-center justify-between text-sm">
                  <span className="text-gray-700 dark:text-gray-300">{file.name}</span>
                  <span className="text-gray-500 dark:text-gray-400">
                    {(file.size / 1024 / 1024).toFixed(2)} MB
                  </span>
                </li>
              ))}
            </ul>
            <button
              onClick={handleConvert}
              disabled={converting}
              className="mt-4 w-full bg-blue-600 hover:bg-blue-700 text-white font-semibold py-3 px-6 rounded-lg disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
            >
              {converting ? 'Submitting...' : 'Convert to LaTeX'}
            </button>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="mt-6 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
            <p className="text-red-700 dark:text-red-300 font-medium">Error: {error}</p>
          </div>
        )}

        {/* Jobs List */}
        {jobs.length > 0 && (
          <div className="mt-8">
            <h2 className="text-2xl font-semibold text-gray-900 dark:text-white mb-4">
              Jobs ({jobs.length})
            </h2>
            <div className="space-y-3">
              {jobs.map((job) => (
                <div
                  key={job.id}
                  className="bg-white dark:bg-gray-800 rounded-lg p-4 border border-gray-200 dark:border-gray-700"
                >
                  <div className="flex items-start justify-between mb-2">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <h3 className="font-semibold text-gray-900 dark:text-white">
                          {job.title || job.filename}
                        </h3>
                        {getStatusBadge(job.status)}
                      </div>
                      <p className="text-sm text-gray-500 dark:text-gray-400">
                        {job.filename} • {new Date(job.created_at * 1000).toLocaleString()}
                      </p>
                    </div>
                    <div className="flex gap-2">
                      {job.status === 'running' || job.status === 'queued' ? (
                        <button
                          onClick={() => handleCancelJob(job.id)}
                          className="bg-red-600 hover:bg-red-700 text-white px-3 py-1.5 rounded text-sm font-medium transition-colors"
                        >
                          Cancel
                        </button>
                      ) : null}
                      {job.status === 'completed' && job.latex && (
                        <>
                          <button
                            onClick={() => handleCopy(job.latex!)}
                            className="bg-gray-100 hover:bg-gray-200 dark:bg-gray-700 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-200 px-3 py-1.5 rounded text-sm font-medium transition-colors"
                          >
                            Copy
                          </button>
                          <button
                            onClick={() => handleDownload(job)}
                            className="bg-blue-600 hover:bg-blue-700 text-white px-3 py-1.5 rounded text-sm font-medium transition-colors"
                          >
                            Download
                          </button>
                          <button
                            onClick={() => setResult(job)}
                            className="bg-green-600 hover:bg-green-700 text-white px-3 py-1.5 rounded text-sm font-medium transition-colors"
                          >
                            View
                          </button>
                        </>
                      )}
                      {(job.status === 'completed' || job.status === 'failed' || job.status === 'cancelled') && (
                        <button
                          onClick={() => handleDeleteJob(job.id)}
                          className="bg-gray-600 hover:bg-gray-700 text-white px-3 py-1.5 rounded text-sm font-medium transition-colors"
                        >
                          Delete
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Progress bar for running jobs */}
                  {job.status === 'running' && job.progress_total > 0 && (
                    <div className="mt-2">
                      <div className="flex justify-between text-xs text-gray-600 dark:text-gray-400 mb-1">
                        <span>{job.current_pass || 'Processing'}</span>
                        <span>Page {job.progress_current}/{job.progress_total}</span>
                      </div>
                      <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
                        <div
                          className="bg-blue-600 h-2 rounded-full transition-all"
                          style={{ width: `${(job.progress_current / job.progress_total) * 100}%` }}
                        ></div>
                      </div>
                    </div>
                  )}

                  {/* Error message */}
                  {job.status === 'failed' && job.error && (
                    <div className="mt-2 text-sm text-red-600 dark:text-red-400">
                      Error: {job.error}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Result Viewer */}
        {result && result.latex && (
          <div className="mt-6 bg-white dark:bg-gray-800 rounded-lg p-6">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-xl font-semibold text-gray-900 dark:text-white">{result.title}</h3>
                <p className="text-sm text-gray-500 dark:text-gray-400">Completed</p>
              </div>
              <button
                onClick={() => setResult(null)}
                className="text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
              >
                Close
              </button>
            </div>
            <pre className="bg-gray-50 dark:bg-gray-900 rounded-lg p-4 text-xs overflow-x-auto max-h-96 overflow-y-auto border border-gray-200 dark:border-gray-700">
              <code className="text-gray-800 dark:text-gray-200">{result.latex}</code>
            </pre>
          </div>
        )}
      </div>
    </div>
  );
}
