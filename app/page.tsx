"use client";

import { useState, useRef, useEffect } from "react";

interface ConversionResult {
  id: string;
  latex: string;
  title: string;
  pages: number;
  filename: string;
  timestamp: number;
}

interface ConversionHistory {
  results: ConversionResult[];
}

export default function Home() {
  const [files, setFiles] = useState<File[]>([]);
  const [converting, setConverting] = useState(false);
  const [result, setResult] = useState<ConversionResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [apiStatus, setApiStatus] = useState<'checking' | 'online' | 'offline'>('checking');
  const [history, setHistory] = useState<ConversionResult[]>([]);
  const [showHistory, setShowHistory] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Load history from localStorage on mount
  useEffect(() => {
    const saved = localStorage.getItem('math-ocr-history');
    if (saved) {
      try {
        const data: ConversionHistory = JSON.parse(saved);
        setHistory(data.results || []);
      } catch (e) {
        console.error('Failed to load history:', e);
      }
    }

    // Check for interrupted conversion
    const inProgress = localStorage.getItem('math-ocr-in-progress');
    if (inProgress) {
      try {
        const { filename, startTime } = JSON.parse(inProgress);
        const elapsed = Math.floor((Date.now() - startTime) / 1000 / 60);
        setError(
          `Looks like a conversion of "${filename}" was interrupted ${elapsed} min ago. ` +
          `Please upload and try again.`
        );
        localStorage.removeItem('math-ocr-in-progress');
      } catch (e) {
        console.error('Failed to restore in-progress state:', e);
      }
    }
  }, []);

  // Save to history
  const saveToHistory = (newResult: Omit<ConversionResult, 'id' | 'timestamp'>) => {
    const result: ConversionResult = {
      ...newResult,
      id: Date.now().toString(),
      timestamp: Date.now(),
    };

    const updatedHistory = [result, ...history].slice(0, 10); // Keep last 10
    setHistory(updatedHistory);
    localStorage.setItem('math-ocr-history', JSON.stringify({ results: updatedHistory }));

    return result;
  };

  // Clear history
  const clearHistory = () => {
    setHistory([]);
    localStorage.removeItem('math-ocr-history');
  };

  // Check API status on mount
  useEffect(() => {
    const checkApi = async () => {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
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
  }, []);

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

    // Mark as in-progress
    localStorage.setItem('math-ocr-in-progress', JSON.stringify({
      filename: file.name,
      startTime: Date.now(),
    }));

    try {
      // Read file as base64
      const base64 = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = (e) => resolve(e.target?.result as string);
        reader.onerror = () => reject(new Error('Failed to read file'));
        reader.readAsDataURL(file);
      });

      const base64Data = base64.split(',')[1]; // Remove data:application/pdf;base64,

      // Call API
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

      let response;
      try {
        response = await fetch(`${apiUrl}/convert`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            pdf_base64: base64Data,
            filename: file.name,
            title: null,
            enable_compile_check: false,
          }),
        });
      } catch (fetchError) {
        throw new Error(
          `Cannot connect to API server at ${apiUrl}. ` +
          `Make sure the Python API is running:\n\n` +
          `  cd math-ocr-app\n` +
          `  uv run uvicorn api_server:app --reload\n\n` +
          `Or set NEXT_PUBLIC_API_URL in .env.local`
        );
      }

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
        throw new Error(errorData.detail || `HTTP ${response.status}`);
      }

      const data = await response.json();

      // Save to history
      const savedResult = saveToHistory({
        latex: data.latex,
        title: data.title,
        pages: data.pages,
        filename: file.name,
      });

      setResult(savedResult);

      // Clear in-progress state on success
      localStorage.removeItem('math-ocr-in-progress');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Conversion failed');
      // Clear in-progress state on error
      localStorage.removeItem('math-ocr-in-progress');
    } finally {
      setConverting(false);
    }
  };

  const handleDownload = () => {
    if (!result) return;
    const blob = new Blob([result.latex], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${result.title}.tex`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleCopy = async () => {
    if (!result) return;
    await navigator.clipboard.writeText(result.latex);
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 dark:from-gray-900 dark:to-gray-800 p-8">
      <div className="max-w-4xl mx-auto">
        {/* API Status Banner */}
        {apiStatus === 'offline' && (
          <div className="mb-6 bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg p-4">
            <div className="flex items-start gap-3">
              <span className="text-2xl">⚠️</span>
              <div className="flex-1">
                <p className="font-semibold text-yellow-800 dark:text-yellow-200 mb-1">
                  API Server Offline
                </p>
                <p className="text-sm text-yellow-700 dark:text-yellow-300 mb-2">
                  The Python API server is not running. Start it with:
                </p>
                <pre className="bg-yellow-100 dark:bg-yellow-900/40 text-yellow-900 dark:text-yellow-100 px-3 py-2 rounded text-xs font-mono">
                  cd math-ocr-app{'\n'}uv run uvicorn api_server:app --reload
                </pre>
              </div>
            </div>
          </div>
        )}
        {apiStatus === 'online' && (
          <div className="mb-6 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg p-3">
            <div className="flex items-center gap-2">
              <span className="text-green-600 dark:text-green-400">✓</span>
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
          <div className="text-6xl mb-4">📄</div>
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
              {converting ? 'Converting...' : 'Convert to LaTeX'}
            </button>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="mt-6 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
            <p className="text-red-700 dark:text-red-300 font-medium">Error: {error}</p>
          </div>
        )}

        {/* Result */}
        {result && (
          <div className="mt-6 bg-white dark:bg-gray-800 rounded-lg p-6">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-xl font-semibold text-gray-900 dark:text-white">{result.title}</h3>
                <p className="text-sm text-gray-500 dark:text-gray-400">{result.pages} pages converted</p>
              </div>
              <div className="flex gap-2">
                <button
                  onClick={handleCopy}
                  className="bg-gray-100 hover:bg-gray-200 dark:bg-gray-700 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-200 px-4 py-2 rounded-lg text-sm font-medium transition-colors"
                >
                  Copy
                </button>
                <button
                  onClick={handleDownload}
                  className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
                >
                  Download .tex
                </button>
              </div>
            </div>
            <pre className="bg-gray-50 dark:bg-gray-900 rounded-lg p-4 text-xs overflow-x-auto max-h-96 overflow-y-auto border border-gray-200 dark:border-gray-700">
              <code className="text-gray-800 dark:text-gray-200">{result.latex}</code>
            </pre>
          </div>
        )}

        {/* History Section */}
        {history.length > 0 && (
          <div className="mt-8">
            <div className="flex items-center justify-between mb-4">
              <button
                onClick={() => setShowHistory(!showHistory)}
                className="flex items-center gap-2 text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white"
              >
                <span className="text-xl">{showHistory ? '📂' : '📁'}</span>
                <h2 className="text-xl font-semibold">
                  Recent Conversions ({history.length})
                </h2>
              </button>
              {showHistory && (
                <button
                  onClick={clearHistory}
                  className="text-sm text-red-600 dark:text-red-400 hover:underline"
                >
                  Clear All
                </button>
              )}
            </div>

            {showHistory && (
              <div className="space-y-3">
                {history.map((item) => (
                  <div
                    key={item.id}
                    className="bg-white dark:bg-gray-800 rounded-lg p-4 border border-gray-200 dark:border-gray-700"
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <h3 className="font-semibold text-gray-900 dark:text-white">
                          {item.title}
                        </h3>
                        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                          {item.filename} • {item.pages} pages • {new Date(item.timestamp).toLocaleString()}
                        </p>
                      </div>
                      <div className="flex gap-2">
                        <button
                          onClick={() => {
                            navigator.clipboard.writeText(item.latex);
                          }}
                          className="bg-gray-100 hover:bg-gray-200 dark:bg-gray-700 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-200 px-3 py-1.5 rounded text-sm font-medium transition-colors"
                        >
                          Copy
                        </button>
                        <button
                          onClick={() => {
                            const blob = new Blob([item.latex], { type: 'text/plain' });
                            const url = URL.createObjectURL(blob);
                            const a = document.createElement('a');
                            a.href = url;
                            a.download = `${item.title}.tex`;
                            a.click();
                            URL.revokeObjectURL(url);
                          }}
                          className="bg-blue-600 hover:bg-blue-700 text-white px-3 py-1.5 rounded text-sm font-medium transition-colors"
                        >
                          Download
                        </button>
                        <button
                          onClick={() => setResult(item)}
                          className="bg-green-600 hover:bg-green-700 text-white px-3 py-1.5 rounded text-sm font-medium transition-colors"
                        >
                          View
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
