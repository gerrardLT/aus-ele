/**
 * WemCsvUploader — WEM CSV/ZIP data upload component
 *
 * Features:
 * - Drag & drop or click to upload
 * - Supports .csv and .zip (AEMO format) files
 * - Auto-detect data type from headers
 * - XHR-based upload with real progress tracking
 * - Result statistics display
 */

import { useState, useRef, useCallback } from 'react';
import { getApiBase } from '../../lib/apiBase';

const API_BASE = getApiBase();

const DATA_TYPES = [
  { value: 'auto', labelZh: '自动识别', labelEn: 'Auto-detect', descZh: '从文件头自动判断数据类型', descEn: 'Auto-detect from file headers' },
  { value: 'trading_price', labelZh: '交易电价 (Trading Price)', labelEn: 'Trading Price', descZh: 'WEM 30分钟交易结算电价', descEn: 'WEM 30-min reference trading price' },
  { value: 'ess_market', labelZh: 'ESS 辅助服务市场价', labelEn: 'ESS Market Price', descZh: 'WEM 必要系统服务市场价格', descEn: 'WEM essential system services market price' },
];

const ACCEPTED_EXTENSIONS = '.csv,.zip';

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

function formatDuration(seconds) {
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}m ${s}s`;
}

export default function WemCsvUploader({ lang = 'zh' }) {
  const [dataType, setDataType] = useState('auto');
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [uploadSpeed, setUploadSpeed] = useState('');
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [dragOver, setDragOver] = useState(false);
  const [selectedFile, setSelectedFile] = useState(null);
  const fileInputRef = useRef(null);
  const xhrRef = useRef(null);

  const zh = lang === 'zh';

  const handleFileSelect = useCallback((file) => {
    if (!file) return;
    const ext = file.name.toLowerCase().split('.').pop();
    if (!['csv', 'zip'].includes(ext)) {
      setError(zh ? '只支持 .csv 和 .zip 文件' : 'Only .csv and .zip files are supported');
      return;
    }
    setSelectedFile(file);
    setResult(null);
    setError(null);
  }, [zh]);

  const handleUpload = useCallback(async () => {
    if (!selectedFile) return;

    setUploading(true);
    setProgress(0);
    setResult(null);
    setError(null);
    setUploadSpeed('');

    const formData = new FormData();
    formData.append('file', selectedFile);

    const url = `${API_BASE}/v1/wem/upload-csv?data_type=${dataType}`;
    const startTime = Date.now();

    try {
      const response = await new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhrRef.current = xhr;

        xhr.upload.addEventListener('progress', (e) => {
          if (e.lengthComputable) {
            const pct = Math.round((e.loaded / e.total) * 95);
            setProgress(pct);
            const elapsed = (Date.now() - startTime) / 1000;
            if (elapsed > 2) {
              const speed = e.loaded / elapsed;
              setUploadSpeed(`${formatBytes(speed)}/s`);
            }
          }
        });

        xhr.onload = () => {
          setProgress(100);
          try {
            const data = JSON.parse(xhr.responseText);
            if (xhr.status >= 200 && xhr.status < 300) {
              resolve(data);
            } else {
              reject(new Error(data.detail || data.message || `HTTP ${xhr.status}`));
            }
          } catch {
            reject(new Error(`HTTP ${xhr.status}: ${xhr.responseText.slice(0, 300)}`));
          }
        };

        xhr.onerror = () => reject(new Error(zh ? '网络连接失败' : 'Network connection failed'));
        xhr.ontimeout = () => reject(new Error(zh ? '上传超时（10分钟限制）' : 'Upload timeout (10min limit)'));
        xhr.onabort = () => reject(new Error(zh ? '已取消' : 'Cancelled'));

        xhr.open('POST', url);
        xhr.timeout = 600_000; // 10 min timeout for large files
        xhr.send(formData);
      });

      setResult(response);
      setSelectedFile(null);
    } catch (err) {
      setError(err.message || (zh ? '上传失败' : 'Upload failed'));
    } finally {
      setUploading(false);
      setProgress(0);
      setUploadSpeed('');
      xhrRef.current = null;
    }
  }, [selectedFile, dataType, zh]);

  const handleCancel = useCallback(() => {
    xhrRef.current?.abort();
  }, []);

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file) handleFileSelect(file);
  }, [handleFileSelect]);

  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface,#fafafa)] p-4">
      {/* Header */}
      <div className="mb-3 flex items-center gap-2">
        <svg className="h-5 w-5 text-[var(--color-primary)]" viewBox="0 0 20 20" fill="currentColor">
          <path fillRule="evenodd" d="M3 17a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zM6.293 6.707a1 1 0 010-1.414l3-3a1 1 0 011.414 0l3 3a1 1 0 01-1.414 1.414L11 5.414V13a1 1 0 11-2 0V5.414L7.707 6.707a1 1 0 01-1.414 0z" clipRule="evenodd" />
        </svg>
        <h3 className="text-sm font-semibold text-[var(--color-text)]">
          {zh ? 'WEM 数据导入' : 'WEM Data Import'}
        </h3>
        <span className="ml-auto text-xs text-[var(--color-muted)]">
          {zh ? '支持 CSV / ZIP' : 'CSV / ZIP supported'}
        </span>
      </div>

      {/* Data type selector */}
      <div className="mb-3">
        <select
          value={dataType}
          onChange={(e) => setDataType(e.target.value)}
          disabled={uploading}
          className="w-full rounded border border-[var(--color-border)] bg-white px-3 py-1.5 text-sm text-[var(--color-text)] focus:border-[var(--color-primary)] focus:outline-none"
        >
          {DATA_TYPES.map((dt) => (
            <option key={dt.value} value={dt.value}>
              {zh ? dt.labelZh : dt.labelEn}
            </option>
          ))}
        </select>
        <p className="mt-1 text-xs text-[var(--color-muted)]">
          {zh
            ? DATA_TYPES.find((d) => d.value === dataType)?.descZh
            : DATA_TYPES.find((d) => d.value === dataType)?.descEn}
        </p>
      </div>

      {/* Drop zone / File info */}
      {!selectedFile ? (
        <div
          onDrop={handleDrop}
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onClick={() => !uploading && fileInputRef.current?.click()}
          className={`
            cursor-pointer rounded-lg border-2 border-dashed p-5 text-center transition-colors
            ${dragOver ? 'border-[var(--color-primary)] bg-[var(--color-primary)]/5' : 'border-[var(--color-border)] hover:border-[var(--color-primary)]/50'}
            ${uploading ? 'pointer-events-none opacity-60' : ''}
          `}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept={ACCEPTED_EXTENSIONS}
            onChange={(e) => { handleFileSelect(e.target.files?.[0]); e.target.value = ''; }}
            className="hidden"
          />
          <svg className="mx-auto mb-2 h-8 w-8 text-[var(--color-muted)]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 16.5V9.75m0 0l3 3m-3-3l-3 3M6.75 19.5a4.5 4.5 0 01-1.41-8.775 5.25 5.25 0 0110.233-2.33 3 3 0 013.758 3.848A3.752 3.752 0 0118 19.5H6.75z" />
          </svg>
          <p className="text-sm text-[var(--color-text)]">
            {zh ? '拖拽或点击上传 CSV / ZIP 文件' : 'Drag & drop or click to upload CSV / ZIP'}
          </p>
          <p className="mt-1 text-xs text-[var(--color-muted)]">
            {zh ? 'AEMO WEM 格式，最大 2GB' : 'AEMO WEM format, max 2GB'}
          </p>
        </div>
      ) : (
        <div className="rounded-lg border border-[var(--color-border)] bg-white p-3">
          <div className="flex items-center gap-2">
            <svg className="h-5 w-5 flex-shrink-0 text-[var(--color-muted)]" viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4z" clipRule="evenodd" />
            </svg>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium text-[var(--color-text)]">{selectedFile.name}</p>
              <p className="text-xs text-[var(--color-muted)]">{formatBytes(selectedFile.size)}</p>
            </div>
            {!uploading && (
              <button onClick={() => setSelectedFile(null)} className="text-xs text-[var(--color-muted)] hover:text-red-500">
                {zh ? '移除' : 'Remove'}
              </button>
            )}
          </div>
          {!uploading && (
            <button
              onClick={handleUpload}
              className="mt-2 w-full rounded bg-[var(--color-primary)] px-4 py-2 text-sm font-medium text-white hover:opacity-90 transition-opacity"
            >
              {zh ? '开始导入' : 'Start Import'}
            </button>
          )}
        </div>
      )}

      {/* Progress bar */}
      {uploading && (
        <div className="mt-3">
          <div className="flex items-center justify-between text-xs text-[var(--color-muted)]">
            <span>{progress}%</span>
            {uploadSpeed && <span>{uploadSpeed}</span>}
            <button onClick={handleCancel} className="text-red-500 hover:underline">
              {zh ? '取消' : 'Cancel'}
            </button>
          </div>
          <div className="mt-1 h-2 overflow-hidden rounded-full bg-[var(--color-border)]">
            <div
              className="h-full rounded-full bg-[var(--color-primary)] transition-all duration-300"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="mt-3 rounded border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Success result */}
      {result && (
        <div className="mt-3 rounded border border-emerald-300 bg-emerald-50 px-3 py-2">
          <p className="text-sm font-medium text-emerald-800">
            {zh ? '导入成功' : 'Import Successful'}
          </p>
          <div className="mt-1 grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-emerald-700">
            <span>{zh ? '数据类型' : 'Data type'}:</span>
            <span className="font-medium">
              {result.data_type === 'trading_price' ? (zh ? '交易电价' : 'Trading Price') : (zh ? 'ESS 市场价' : 'ESS Market')}
            </span>
            <span>{zh ? '导入行数' : 'Rows imported'}:</span>
            <span className="font-mono font-semibold">{result.rows_imported?.toLocaleString()}</span>
            <span>{zh ? '跳过行数' : 'Rows skipped'}:</span>
            <span className="font-mono">{result.rows_skipped}</span>
            <span>{zh ? '时间范围' : 'Time range'}:</span>
            <span className="font-mono text-[10px]">{result.min_interval} ~ {result.max_interval}</span>
            <span>{zh ? '文件大小' : 'File size'}:</span>
            <span className="font-mono">{result.file_size_mb} MB</span>
            <span>{zh ? '耗时' : 'Duration'}:</span>
            <span className="font-mono">{formatDuration(result.elapsed_seconds)}</span>
          </div>
        </div>
      )}
    </div>
  );
}
