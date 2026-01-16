import React, { useState, useEffect, useRef } from 'react';
import { Upload, Download, Trash2, Play, Pause, CheckCircle, XCircle, Filter, Search } from 'lucide-react';

/**
 * Facebook Profile URL Processor
 * Transforms Marketplace URLs, fetches actual pages, extracts metadata
 */
export default function FacebookProfileProcessor() {
  const [profiles, setProfiles] = useState([]);
  const [isProcessing, setIsProcessing] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [progress, setProgress] = useState({ current: 0, total: 0, success: 0, errors: 0 });
  const [filterStatus, setFilterStatus] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [notification, setNotification] = useState(null);
  const fileInputRef = useRef(null);
  const processingRef = useRef(false);
  const pausedRef = useRef(false);

  // Load data from persistent storage on mount
  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const result = await window.storage.get('fb_profiles');
      if (result && result.value) {
        setProfiles(JSON.parse(result.value));
      }
    } catch (error) {
      console.log('No existing data found');
    }
  };

  const saveData = async (data) => {
    try {
      await window.storage.set('fb_profiles', JSON.stringify(data), false);
    } catch (error) {
      showNotification('Failed to save data', 'error');
    }
  };

  const showNotification = (message, type = 'success') => {
    setNotification({ message, type });
    setTimeout(() => setNotification(null), 3000);
  };

  // Transform URL from marketplace format to clean profile format
  const transformURL = (url) => {
    const match = url.match(/marketplace\/profile\/(\d+)/);
    if (match) {
      return {
        clean: `https://www.facebook.com/${match[1]}`,
        id: match[1],
        valid: true
      };
    }
    return { clean: null, id: null, valid: false };
  };

  // Parse HTML metadata from response
  const parseHTMLMetadata = (html) => {
    const metadata = {
      title: null,
      og_title: null,
      og_description: null
    };

    try {
      // Extract page title
      const titleMatch = html.match(/<title[^>]*>([^<]+)<\/title>/i);
      if (titleMatch) {
        metadata.title = titleMatch[1].trim();
      }

      // Extract OpenGraph title
      const ogTitleMatch = html.match(/<meta[^>]+property=["']og:title["'][^>]+content=["']([^"']+)["']/i);
      if (ogTitleMatch) {
        metadata.og_title = ogTitleMatch[1].trim();
      }

      // Extract OpenGraph description
      const ogDescMatch = html.match(/<meta[^>]+property=["']og:description["'][^>]+content=["']([^"']+)["']/i);
      if (ogDescMatch) {
        metadata.og_description = ogDescMatch[1].trim();
      }
    } catch (error) {
      console.error('HTML parsing error:', error);
    }

    return metadata;
  };

  // Fetch and extract profile data via HTTP
  const fetchProfileData = async (cleanUrl, profileId) => {
    try {
      // Attempt to fetch the URL
      const response = await fetch(cleanUrl, {
        method: 'GET',
        headers: {
          'User-Agent': 'Mozilla/5.0 (compatible; profile-resolver/1.0)'
        },
        mode: 'cors'
      });

      const html = await response.text();
      const metadata = parseHTMLMetadata(html);

      return {
        resolved_url: response.url,
        http_status: response.status,
        page_title: metadata.title,
        og_title: metadata.og_title,
        og_description: metadata.og_description,
        status: 'success'
      };
    } catch (error) {
      // CORS will block direct fetches, so we acknowledge this limitation
      return {
        resolved_url: cleanUrl,
        http_status: null,
        page_title: null,
        og_title: null,
        og_description: null,
        error: 'CORS blocked - Browser security prevents direct fetching. Profile ID: ' + profileId,
        status: 'error'
      };
    }
  };

  // Process URLs from uploaded file
  const handleFileUpload = async (event) => {
    const file = event.target.files[0];
    if (!file) return;

    try {
      const text = await file.text();
      const urls = text.split('\n')
        .map(line => line.trim())
        .filter(line => line && line.startsWith('http'));

      if (urls.length === 0) {
        showNotification('No valid URLs found in file', 'error');
        return;
      }

      // Transform URLs and check for duplicates
      const newProfiles = [];
      const existingIds = new Set(profiles.map(p => p.profile_id));

      urls.forEach((url, index) => {
        const transformed = transformURL(url);
        if (transformed.valid && !existingIds.has(transformed.id)) {
          newProfiles.push({
            id: Date.now() + index,
            original_url: url,
            clean_url: transformed.clean,
            profile_id: transformed.id,
            resolved_url: null,
            http_status: null,
            page_title: null,
            og_title: null,
            og_description: null,
            status: 'pending',
            fetched_at: null,
            error: null
          });
          existingIds.add(transformed.id);
        }
      });

      if (newProfiles.length === 0) {
        showNotification('All URLs already processed or invalid', 'error');
        return;
      }

      const updatedProfiles = [...profiles, ...newProfiles];
      setProfiles(updatedProfiles);
      await saveData(updatedProfiles);
      setProgress(prev => ({ ...prev, total: updatedProfiles.filter(p => p.status === 'pending').length }));
      showNotification(`Added ${newProfiles.length} URLs to process`, 'success');
    } catch (error) {
      showNotification('Failed to read file', 'error');
    }
  };

  // Start processing URLs
  const startProcessing = async () => {
    if (processingRef.current) return;
    
    processingRef.current = true;
    pausedRef.current = false;
    setIsProcessing(true);
    setIsPaused(false);

    const pendingProfiles = profiles.filter(p => p.status === 'pending');
    setProgress({ current: 0, total: pendingProfiles.length, success: 0, errors: 0 });

    for (let i = 0; i < pendingProfiles.length; i++) {
      if (pausedRef.current) {
        setIsPaused(true);
        break;
      }

      const profile = pendingProfiles[i];
      
      // Update status to processing
      const updatingProfiles = profiles.map(p => 
        p.id === profile.id ? { ...p, status: 'processing' } : p
      );
      setProfiles(updatingProfiles);

      // Fetch data with retry logic
      let attempts = 0;
      let result = null;
      
      while (attempts < 3 && !result) {
        try {
          result = await fetchProfileData(profile.clean_url, profile.profile_id);
          break;
        } catch (error) {
          attempts++;
          if (attempts === 3) {
            result = {
              resolved_url: profile.clean_url,
              http_status: null,
              page_title: null,
              og_title: null,
              og_description: null,
              error: 'Failed after 3 attempts: ' + error.message,
              status: 'error'
            };
          } else {
            await new Promise(resolve => setTimeout(resolve, 2000));
          }
        }
      }

      // Update profile with results
      const updatedProfiles = profiles.map(p => {
        if (p.id === profile.id) {
          return {
            ...p,
            resolved_url: result.resolved_url,
            http_status: result.http_status,
            page_title: result.page_title,
            og_title: result.og_title,
            og_description: result.og_description,
            status: result.status === 'error' ? 'error' : 'success',
            fetched_at: new Date().toISOString(),
            error: result.error || null
          };
        }
        return p;
      });

      setProfiles(updatedProfiles);
      await saveData(updatedProfiles);

      setProgress(prev => ({
        current: i + 1,
        total: pendingProfiles.length,
        success: result.status === 'error' ? prev.success : prev.success + 1,
        errors: result.status === 'error' ? prev.errors + 1 : prev.errors
      }));

      // Rate limiting: 1 request per second
      if (i < pendingProfiles.length - 1) {
        await new Promise(resolve => setTimeout(resolve, 1000));
      }
    }

    processingRef.current = false;
    if (!pausedRef.current) {
      setIsProcessing(false);
      showNotification('Processing complete!', 'success');
    }
  };

  const pauseProcessing = () => {
    pausedRef.current = true;
    setIsPaused(true);
    setIsProcessing(false);
  };

  const resumeProcessing = () => {
    startProcessing();
  };

  // Export functions
  const exportJSON = () => {
    const dataStr = JSON.stringify(profiles, null, 2);
    downloadFile(dataStr, 'facebook_profiles.json', 'application/json');
    showNotification('Exported as JSON', 'success');
  };

  const exportCSV = () => {
    const headers = ['Profile ID', 'Original URL', 'Clean URL', 'Resolved URL', 'HTTP Status', 'Page Title', 'OG Title', 'OG Description', 'Status', 'Fetched At', 'Error'];
    const rows = profiles.map(p => [
      p.profile_id,
      p.original_url,
      p.clean_url,
      p.resolved_url || '',
      p.http_status || '',
      (p.page_title || '').replace(/"/g, '""'),
      (p.og_title || '').replace(/"/g, '""'),
      (p.og_description || '').replace(/"/g, '""'),
      p.status,
      p.fetched_at || '',
      (p.error || '').replace(/"/g, '""')
    ]);
    
    const csvContent = [
      headers.join(','),
      ...rows.map(row => row.map(cell => `"${cell}"`).join(','))
    ].join('\n');
    
    downloadFile(csvContent, 'facebook_profiles.csv', 'text/csv');
    showNotification('Exported as CSV', 'success');
  };

  const exportSQL = () => {
    const sqlStatements = [
      'CREATE TABLE IF NOT EXISTS profiles (',
      '  id INTEGER PRIMARY KEY AUTOINCREMENT,',
      '  original_url TEXT NOT NULL,',
      '  clean_url TEXT,',
      '  profile_id TEXT,',
      '  resolved_url TEXT,',
      '  http_status INTEGER,',
      '  page_title TEXT,',
      '  og_title TEXT,',
      '  og_description TEXT,',
      '  status TEXT,',
      '  fetched_at TEXT,',
      '  error TEXT',
      ');',
      ''
    ];

    profiles.forEach((p, index) => {
      const values = [
        p.original_url,
        p.clean_url,
        p.profile_id,
        p.resolved_url || 'NULL',
        p.http_status || 'NULL',
        p.page_title || 'NULL',
        p.og_title || 'NULL',
        p.og_description || 'NULL',
        p.status,
        p.fetched_at || 'NULL',
        p.error || 'NULL'
      ].map(v => v === 'NULL' ? 'NULL' : `'${String(v).replace(/'/g, "''")}'`);

      sqlStatements.push(`INSERT INTO profiles (original_url, clean_url, profile_id, resolved_url, http_status, page_title, og_title, og_description, status, fetched_at, error) VALUES (${values.join(', ')});`);
    });

    const sqlContent = sqlStatements.join('\n');
    downloadFile(sqlContent, 'facebook_profiles.sql', 'text/plain');
    showNotification('Exported as SQL', 'success');
  };

  const downloadFile = (content, filename, type) => {
    const blob = new Blob([content], { type });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  };

  const resetAllData = async () => {
    if (window.confirm('Are you sure you want to delete all data? This cannot be undone.')) {
      try {
        await window.storage.delete('fb_profiles');
        setProfiles([]);
        setProgress({ current: 0, total: 0, success: 0, errors: 0 });
        showNotification('All data cleared', 'success');
      } catch (error) {
        showNotification('Failed to clear data', 'error');
      }
    }
  };

  // Filter and search
  const filteredProfiles = profiles.filter(p => {
    const matchesStatus = filterStatus === 'all' || p.status === filterStatus;
    const matchesSearch = !searchQuery || 
      (p.og_title && p.og_title.toLowerCase().includes(searchQuery.toLowerCase())) ||
      (p.page_title && p.page_title.toLowerCase().includes(searchQuery.toLowerCase())) ||
      (p.profile_id && p.profile_id.includes(searchQuery));
    return matchesStatus && matchesSearch;
  });

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-indigo-950 to-slate-900 p-4 md:p-8">
      {/* Notification Toast */}
      {notification && (
        <div className={`fixed top-4 right-4 z-50 px-6 py-4 rounded-lg shadow-2xl transform transition-all duration-300 ${
          notification.type === 'success' 
            ? 'bg-emerald-500 text-white' 
            : 'bg-rose-500 text-white'
        }`}>
          <div className="flex items-center gap-3">
            {notification.type === 'success' ? <CheckCircle size={20} /> : <XCircle size={20} />}
            <span className="font-medium">{notification.message}</span>
          </div>
        </div>
      )}

      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-5xl font-bold text-white mb-3 tracking-tight">
            Profile <span className="text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 to-blue-500">Processor</span>
          </h1>
          <p className="text-slate-400 text-lg">Transform URLs, fetch metadata, store in database format</p>
        </div>

        {/* CORS Warning */}
        <div className="bg-amber-900/20 border border-amber-700 rounded-xl p-4 mb-6">
          <div className="flex gap-3">
            <XCircle size={20} className="text-amber-400 flex-shrink-0 mt-0.5" />
            <div className="text-sm text-amber-200">
              <strong>Browser Limitation:</strong> Direct HTTP fetching is blocked by CORS. This app demonstrates the architecture but cannot fetch Facebook pages directly. For production use, implement server-side fetching or use the Python script approach.
            </div>
          </div>
        </div>

        {/* Control Panel */}
        <div className="bg-slate-900/50 backdrop-blur-xl rounded-2xl border border-slate-800 p-6 mb-6 shadow-2xl">
          <div className="flex flex-wrap gap-3">
            <button
              onClick={() => fileInputRef.current?.click()}
              className="flex items-center gap-2 px-5 py-3 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white rounded-xl font-medium transition-all duration-200 shadow-lg hover:shadow-xl transform hover:scale-105"
            >
              <Upload size={20} />
              Upload URLs
            </button>
            <input
              ref={fileInputRef}
              type="file"
              accept=".txt"
              onChange={handleFileUpload}
              className="hidden"
            />

            {!isProcessing && !isPaused && profiles.some(p => p.status === 'pending') && (
              <button
                onClick={startProcessing}
                className="flex items-center gap-2 px-5 py-3 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white rounded-xl font-medium transition-all duration-200 shadow-lg hover:shadow-xl transform hover:scale-105"
              >
                <Play size={20} />
                Start Processing
              </button>
            )}

            {isProcessing && (
              <button
                onClick={pauseProcessing}
                className="flex items-center gap-2 px-5 py-3 bg-gradient-to-r from-amber-600 to-orange-600 hover:from-amber-500 hover:to-orange-500 text-white rounded-xl font-medium transition-all duration-200 shadow-lg hover:shadow-xl transform hover:scale-105"
              >
                <Pause size={20} />
                Pause
              </button>
            )}

            {isPaused && (
              <button
                onClick={resumeProcessing}
                className="flex items-center gap-2 px-5 py-3 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white rounded-xl font-medium transition-all duration-200 shadow-lg hover:shadow-xl transform hover:scale-105"
              >
                <Play size={20} />
                Resume
              </button>
            )}

            {profiles.length > 0 && (
              <>
                <button
                  onClick={exportJSON}
                  className="flex items-center gap-2 px-5 py-3 bg-slate-700 hover:bg-slate-600 text-white rounded-xl font-medium transition-all duration-200"
                >
                  <Download size={20} />
                  Export JSON
                </button>

                <button
                  onClick={exportCSV}
                  className="flex items-center gap-2 px-5 py-3 bg-slate-700 hover:bg-slate-600 text-white rounded-xl font-medium transition-all duration-200"
                >
                  <Download size={20} />
                  Export CSV
                </button>

                <button
                  onClick={exportSQL}
                  className="flex items-center gap-2 px-5 py-3 bg-slate-700 hover:bg-slate-600 text-white rounded-xl font-medium transition-all duration-200"
                >
                  <Download size={20} />
                  Export SQL
                </button>

                <button
                  onClick={resetAllData}
                  className="flex items-center gap-2 px-5 py-3 bg-rose-900/50 hover:bg-rose-800 text-rose-200 rounded-xl font-medium transition-all duration-200 ml-auto"
                >
                  <Trash2 size={20} />
                  Reset All
                </button>
              </>
            )}
          </div>

          {/* Progress Bar */}
          {progress.total > 0 && (
            <div className="mt-6">
              <div className="flex justify-between text-sm text-slate-400 mb-2">
                <span>Progress: {progress.current} / {progress.total}</span>
                <span>Success: {progress.success} | Errors: {progress.errors}</span>
              </div>
              <div className="w-full h-3 bg-slate-800 rounded-full overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-cyan-500 to-blue-500 transition-all duration-500 ease-out"
                  style={{ width: `${(progress.current / progress.total) * 100}%` }}
                />
              </div>
            </div>
          )}
        </div>

        {/* Filters */}
        {profiles.length > 0 && (
          <div className="bg-slate-900/50 backdrop-blur-xl rounded-2xl border border-slate-800 p-4 mb-6">
            <div className="flex flex-wrap gap-4">
              <div className="flex items-center gap-2">
                <Filter size={18} className="text-slate-400" />
                <select
                  value={filterStatus}
                  onChange={(e) => setFilterStatus(e.target.value)}
                  className="px-4 py-2 bg-slate-800 text-slate-200 rounded-lg border border-slate-700 focus:border-blue-500 focus:outline-none"
                >
                  <option value="all">All Status</option>
                  <option value="pending">Pending</option>
                  <option value="processing">Processing</option>
                  <option value="success">Success</option>
                  <option value="error">Error</option>
                </select>
              </div>

              <div className="flex items-center gap-2 flex-1 max-w-md">
                <Search size={18} className="text-slate-400" />
                <input
                  type="text"
                  placeholder="Search by title or profile ID..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="flex-1 px-4 py-2 bg-slate-800 text-slate-200 rounded-lg border border-slate-700 focus:border-blue-500 focus:outline-none placeholder-slate-500"
                />
              </div>
            </div>
          </div>
        )}

        {/* Results Table */}
        {profiles.length > 0 ? (
          <div className="bg-slate-900/50 backdrop-blur-xl rounded-2xl border border-slate-800 overflow-hidden shadow-2xl">
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="bg-slate-800/50 border-b border-slate-700">
                    <th className="px-6 py-4 text-left text-sm font-semibold text-slate-300">Profile ID</th>
                    <th className="px-6 py-4 text-left text-sm font-semibold text-slate-300">Page Title</th>
                    <th className="px-6 py-4 text-left text-sm font-semibold text-slate-300">OG Title</th>
                    <th className="px-6 py-4 text-left text-sm font-semibold text-slate-300">HTTP Status</th>
                    <th className="px-6 py-4 text-left text-sm font-semibold text-slate-300">Status</th>
                    <th className="px-6 py-4 text-left text-sm font-semibold text-slate-300">URL</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredProfiles.map((profile, index) => (
                    <tr
                      key={profile.id}
                      className={`border-b border-slate-800 hover:bg-slate-800/30 transition-colors ${
                        index % 2 === 0 ? 'bg-slate-900/20' : ''
                      }`}
                    >
                      <td className="px-6 py-4 text-slate-300 font-mono text-sm">{profile.profile_id}</td>
                      <td className="px-6 py-4 text-slate-200 font-medium max-w-xs truncate">
                        {profile.page_title || '-'}
                      </td>
                      <td className="px-6 py-4 text-slate-400 text-sm max-w-xs truncate">
                        {profile.og_title || '-'}
                      </td>
                      <td className="px-6 py-4 text-slate-300 text-sm">
                        {profile.http_status || '-'}
                      </td>
                      <td className="px-6 py-4">
                        <span className={`inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-medium ${
                          profile.status === 'success' ? 'bg-emerald-900/50 text-emerald-300' :
                          profile.status === 'error' ? 'bg-rose-900/50 text-rose-300' :
                          profile.status === 'processing' ? 'bg-blue-900/50 text-blue-300' :
                          'bg-slate-700 text-slate-300'
                        }`}>
                          {profile.status === 'success' && <CheckCircle size={12} />}
                          {profile.status === 'error' && <XCircle size={12} />}
                          {profile.status.charAt(0).toUpperCase() + profile.status.slice(1)}
                        </span>
                      </td>
                      <td className="px-6 py-4">
                        <a
                          href={profile.clean_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-cyan-400 hover:text-cyan-300 text-sm hover:underline"
                        >
                          View Profile
                        </a>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {filteredProfiles.length === 0 && (
              <div className="text-center py-12 text-slate-500">
                No profiles match your filters
              </div>
            )}
          </div>
        ) : (
          <div className="bg-slate-900/50 backdrop-blur-xl rounded-2xl border border-slate-800 p-12 text-center">
            <Upload size={48} className="mx-auto text-slate-600 mb-4" />
            <h3 className="text-xl font-semibold text-slate-300 mb-2">No URLs Loaded</h3>
            <p className="text-slate-500 mb-6">Upload a .txt file containing Facebook Marketplace profile URLs to get started</p>
            <button
              onClick={() => fileInputRef.current?.click()}
              className="inline-flex items-center gap-2 px-6 py-3 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white rounded-xl font-medium transition-all duration-200 shadow-lg hover:shadow-xl transform hover:scale-105"
            >
              <Upload size={20} />
              Upload File
            </button>
          </div>
        )}

        {/* Stats Footer */}
        {profiles.length > 0 && (
          <div className="mt-6 grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="bg-slate-900/50 backdrop-blur-xl rounded-xl border border-slate-800 p-4">
              <div className="text-slate-500 text-sm mb-1">Total</div>
              <div className="text-2xl font-bold text-white">{profiles.length}</div>
            </div>
            <div className="bg-emerald-900/20 backdrop-blur-xl rounded-xl border border-emerald-800 p-4">
              <div className="text-emerald-400 text-sm mb-1">Success</div>
              <div className="text-2xl font-bold text-emerald-300">
                {profiles.filter(p => p.status === 'success').length}
              </div>
            </div>
            <div className="bg-rose-900/20 backdrop-blur-xl rounded-xl border border-rose-800 p-4">
              <div className="text-rose-400 text-sm mb-1">Errors</div>
              <div className="text-2xl font-bold text-rose-300">
                {profiles.filter(p => p.status === 'error').length}
              </div>
            </div>
            <div className="bg-slate-900/50 backdrop-blur-xl rounded-xl border border-slate-800 p-4">
              <div className="text-slate-500 text-sm mb-1">Pending</div>
              <div className="text-2xl font-bold text-slate-300">
                {profiles.filter(p => p.status === 'pending').length}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}