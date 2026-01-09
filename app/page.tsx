"use client";

import { useState, useRef, useEffect } from "react";
import { signIn, useSession } from "next-auth/react";

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

interface UserInfo {
  id: string;
  email: string;
  name: string | null;
  tier: string;
  usage_24h: number;
  limit: number;
}

export default function Home() {
  const { data: session, status: sessionStatus } = useSession();
  const [files, setFiles] = useState<File[]>([]);
  const [converting, setConverting] = useState(false);
  const [result, setResult] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [apiStatus, setApiStatus] = useState<"checking" | "online" | "offline">("checking");
  const [jobs, setJobs] = useState<Job[]>([]);
  const [userInfo, setUserInfo] = useState<UserInfo | null>(null);
  const [upgrading, setUpgrading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

  async function getAuthToken(): Promise<string | null> {
    if (!session?.user) return null;

    try {
      const response = await fetch('/api/token');
      if (!response.ok) return null;

      const data = await response.json();
      return data.token;
    } catch (err) {
      console.error('Failed to get auth token:', err);
      return null;
    }
  }

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

  // Fetch user info on login
  useEffect(() => {
    if (!session?.user) {
      setUserInfo(null);
      return;
    }

    const fetchUserInfo = async () => {
      try {
        const token = await getAuthToken();
        if (!token) return;

        const response = await fetch(`${apiUrl}/users/me`, {
          headers: { Authorization: `Bearer ${token}` },
        });

        if (response.ok) {
          const data = await response.json();
          setUserInfo(data);
        }
      } catch (err) {
        console.error('Failed to fetch user info:', err);
      }
    };

    fetchUserInfo();
  }, [session, apiUrl]);

  // Poll jobs every 2 seconds
  useEffect(() => {
    if (!session?.user) {
      setJobs([]);
      return;
    }

    const fetchJobs = async () => {
      try {
        const token = await getAuthToken();
        if (!token) return;

        const response = await fetch(`${apiUrl}/jobs?limit=50`, {
          headers: { Authorization: `Bearer ${token}` },
        });

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
  }, [session, apiUrl]);

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

    try {
      const token = await getAuthToken();
      if (!token) {
        throw new Error('Not authenticated');
      }

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
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
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

      // Refresh user info to update usage
      const userResponse = await fetch(`${apiUrl}/users/me`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (userResponse.ok) {
        setUserInfo(await userResponse.json());
      }

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
      const token = await getAuthToken();
      if (!token) return;

      const response = await fetch(`${apiUrl}/jobs/${jobId}/cancel`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
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
      const token = await getAuthToken();
      if (!token) return;

      const response = await fetch(`${apiUrl}/jobs/${jobId}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) {
        throw new Error('Failed to delete job');
      }
    } catch (err) {
      console.error('Failed to delete job:', err);
    }
  };

  const handleUpgrade = async () => {
    setUpgrading(true);
    try {
      const response = await fetch('/api/stripe/create-checkout', {
        method: 'POST',
      });

      if (!response.ok) {
        throw new Error('Failed to create checkout session');
      }

      const { url } = await response.json();
      if (url) {
        window.location.href = url;
      }
    } catch (err) {
      console.error('Failed to upgrade:', err);
      setError('Failed to start upgrade process');
    } finally {
      setUpgrading(false);
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
      queued: "bg-stone-100 text-stone-700",
      running: "bg-amber-100 text-amber-700",
      completed: "bg-emerald-100 text-emerald-700",
      failed: "bg-rose-100 text-rose-700",
      cancelled: "bg-stone-200 text-stone-700",
    };
    return (
      <span className={`px-2 py-1 rounded-full text-xs font-semibold ${styles[status] || styles.queued}`}>
        {status.toUpperCase()}
      </span>
    );
  };

  // Show loading while checking auth
  if (sessionStatus === "loading") {
    return (
      <div className="flex items-center justify-center min-h-[calc(100vh-76px)]">
        <p className="text-stone-500">Loading...</p>
      </div>
    );
  }

  // Show login prompt if not authenticated
  if (!session?.user) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[calc(100vh-76px)] px-6 py-16">
        <div className="max-w-2xl text-center">
          <p className="text-sm uppercase tracking-[0.25em] text-stone-400 mb-4">
            PDF to LaTeX
          </p>
          <h1 className="text-4xl md:text-5xl font-semibold tracking-tight text-stone-900 mb-4">
            Clean LaTeX from handwritten math
          </h1>
          <p className="text-base md:text-lg text-stone-600 mb-8">
            Upload a PDF and get tidy, editable LaTeX. Sign in with Google to
            start your first conversion.
          </p>
          <div className="flex items-center justify-center gap-4">
            <button
              onClick={() => signIn("google")}
              className="px-6 py-3 rounded-full bg-stone-900 text-white text-sm font-medium hover:bg-stone-800"
            >
              Sign in with Google
            </button>
            <span className="text-sm text-stone-500">
              Free tier: 3 PDFs per day
            </span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="px-6 py-10">
      <div className="max-w-4xl mx-auto">
        <div className="flex flex-col gap-6">
          {/* Status + Usage */}
          <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
            {userInfo && (
              <div className="flex items-center gap-3 rounded-full border border-stone-200 bg-white px-4 py-2 text-sm text-stone-600">
                <span className="font-medium text-stone-900">
                  {userInfo.tier === "unlimited"
                    ? "Unlimited"
                    : userInfo.tier === "paid"
                    ? "Pro"
                    : "Free"}
                </span>
                <span className="text-stone-400">|</span>
                <span>
                  {userInfo.tier === "unlimited"
                    ? "No limits today"
                    : `${userInfo.usage_24h}/${userInfo.limit} conversions used`}
                </span>
              </div>
            )}
            {userInfo?.tier === "free" && (
              <button
                onClick={handleUpgrade}
                disabled={upgrading}
                className="px-5 py-2 rounded-full border border-stone-900 text-stone-900 text-sm font-medium hover:bg-stone-900 hover:text-white disabled:border-stone-300 disabled:text-stone-400 disabled:hover:bg-transparent"
              >
                {upgrading ? "Loading..." : "Upgrade to Pro $9.99/mo"}
              </button>
            )}
          </div>

          {/* API Status */}
          {apiStatus !== "checking" && (
            <div className="flex items-center gap-3 text-sm text-stone-600">
              <span
                className={`inline-flex h-2.5 w-2.5 rounded-full ${
                  apiStatus === "online" ? "bg-emerald-500" : "bg-amber-400"
                }`}
              />
              <span>
                {apiStatus === "online" ? "API server online" : "API server offline"}
              </span>
              {apiStatus === "offline" && (
                <span className="text-stone-400">
                  Run `./start.sh` to start the backend.
                </span>
              )}
            </div>
          )}
        </div>

        <div className="mt-8">
          <h1 className="text-3xl md:text-4xl font-semibold tracking-tight text-stone-900 mb-2">
            Upload a PDF
          </h1>
          <p className="text-stone-600 mb-6">
            Convert handwritten math into clean LaTeX in a few minutes.
          </p>
        </div>

        {/* Upload Zone */}
        <div
          className="rounded-2xl border border-stone-200 bg-white/80 p-10 text-center shadow-sm hover:border-stone-300 transition-colors cursor-pointer"
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
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-stone-100 text-stone-700 text-sm font-semibold">
            PDF
          </div>
          <p className="text-base text-stone-700 mb-1">
            Drop a PDF here or click to browse
          </p>
          <p className="text-sm text-stone-500">
            Supports single or multiple files
          </p>
        </div>

        {/* File List */}
        {files.length > 0 && (
          <div className="mt-6 bg-white rounded-xl border border-stone-200 p-4">
            <h3 className="font-semibold text-stone-900 mb-3">
              Selected files
            </h3>
            <ul className="space-y-2">
              {files.map((file, i) => (
                <li key={i} className="flex items-center justify-between text-sm">
                  <span className="text-stone-700">{file.name}</span>
                  <span className="text-stone-500">
                    {(file.size / 1024 / 1024).toFixed(2)} MB
                  </span>
                </li>
              ))}
            </ul>
            <button
              onClick={handleConvert}
              disabled={converting}
              className="mt-4 w-full bg-stone-900 hover:bg-stone-800 text-white font-semibold py-3 px-6 rounded-xl disabled:bg-stone-400 disabled:cursor-not-allowed transition-colors"
            >
              {converting ? "Submitting..." : "Convert to LaTeX"}
            </button>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="mt-6 bg-red-50 border border-red-200 rounded-lg p-4">
            <p className="text-red-700 font-medium">Error: {error}</p>
          </div>
        )}

        {/* Jobs List */}
        {jobs.length > 0 && (
          <div className="mt-8">
            <h2 className="text-2xl font-semibold text-stone-900 mb-4">
              Jobs ({jobs.length})
            </h2>
            <div className="space-y-3">
              {jobs.map((job) => (
                <div
                  key={job.id}
                  className="bg-white rounded-xl p-4 border border-stone-200"
                >
                  <div className="flex items-start justify-between mb-2">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <h3 className="font-semibold text-stone-900">
                          {job.title || job.filename}
                        </h3>
                        {getStatusBadge(job.status)}
                      </div>
                      <p className="text-sm text-stone-500">
                        {job.filename} • {new Date(job.created_at * 1000).toLocaleString()}
                      </p>
                    </div>
                    <div className="flex gap-2">
                      {job.status === 'running' || job.status === 'queued' ? (
                        <button
                          onClick={() => handleCancelJob(job.id)}
                          className="bg-rose-600 hover:bg-rose-700 text-white px-3 py-1.5 rounded-lg text-sm font-medium transition-colors"
                        >
                          Cancel
                        </button>
                      ) : null}
                      {job.status === 'completed' && job.latex && (
                        <>
                          <button
                            onClick={() => handleCopy(job.latex!)}
                            className="bg-stone-100 hover:bg-stone-200 text-stone-700 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors"
                          >
                            Copy
                          </button>
                          <button
                            onClick={() => handleDownload(job)}
                            className="bg-stone-900 hover:bg-stone-800 text-white px-3 py-1.5 rounded-lg text-sm font-medium transition-colors"
                          >
                            Download
                          </button>
                          <button
                            onClick={() => setResult(job)}
                            className="bg-emerald-600 hover:bg-emerald-700 text-white px-3 py-1.5 rounded-lg text-sm font-medium transition-colors"
                          >
                            View
                          </button>
                        </>
                      )}
                      {(job.status === 'completed' || job.status === 'failed' || job.status === 'cancelled') && (
                        <button
                          onClick={() => handleDeleteJob(job.id)}
                          className="bg-stone-700 hover:bg-stone-800 text-white px-3 py-1.5 rounded-lg text-sm font-medium transition-colors"
                        >
                          Delete
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Progress bar for running jobs */}
                  {job.status === 'running' && job.progress_total > 0 && (
                    <div className="mt-2">
                      <div className="flex justify-between text-xs text-stone-600 mb-1">
                        <span>{job.current_pass || 'Processing'}</span>
                        <span>Page {job.progress_current}/{job.progress_total}</span>
                      </div>
                      <div className="w-full bg-stone-200 rounded-full h-2">
                        <div
                          className="bg-stone-900 h-2 rounded-full transition-all"
                          style={{ width: `${(job.progress_current / job.progress_total) * 100}%` }}
                        ></div>
                      </div>
                    </div>
                  )}

                  {/* Error message */}
                  {job.status === 'failed' && job.error && (
                    <div className="mt-2 text-sm text-red-600">
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
          <div className="mt-6 bg-white rounded-xl p-6 border border-stone-200">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-xl font-semibold text-stone-900">{result.title}</h3>
                <p className="text-sm text-stone-500">Completed</p>
              </div>
              <button
                onClick={() => setResult(null)}
                className="text-stone-500 hover:text-stone-700"
              >
                Close
              </button>
            </div>
            <pre className="bg-stone-50 rounded-lg p-4 text-xs overflow-x-auto max-h-96 overflow-y-auto border border-stone-200">
              <code className="text-stone-800">{result.latex}</code>
            </pre>
          </div>
        )}
      </div>
    </div>
  );
}
