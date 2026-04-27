import { useRef, useState } from 'react';
import '../styles/components.css';

const ICONS = {
  'pdf': '📄', 'docx': '📝', 'doc': '📝',
  'xlsx': '📊', 'xls': '📊', 'csv': '📋',
  'txt': '📃', 'default': '📁'
};

function getIcon(filename) {
  const ext = filename?.split('.').pop()?.toLowerCase();
  return ICONS[ext] || ICONS.default;
}

function formatBytes(bytes) {
  if (!bytes) return '';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function FileDropzone({
  label = 'Drop file here or click to upload',
  subtext = 'Supported formats: PDF, DOCX, XLSX, TXT',
  accept,
  value,
  onChange,
  icon = '☁️',
}) {
  const inputRef = useRef();
  const [dragging, setDragging] = useState(false);

  const handleFile = (file) => {
    if (file) {
      onChange(file);
      if (inputRef.current) {
        inputRef.current.value = '';
      }
    }
  };

  const onDragOver = (e) => { e.preventDefault(); setDragging(true); };
  const onDragLeave = () => setDragging(false);
  const onDrop = (e) => {
    e.preventDefault();
    setDragging(false);
    handleFile(e.dataTransfer.files[0]);
  };

  return (
    <div>
      <div
        className={`dropzone ${dragging ? 'drag-over' : ''} ${value ? 'has-file' : ''}`}
        onClick={() => !value && inputRef.current.click()}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
        style={{ cursor: value ? 'default' : 'pointer' }}
      >
        <input
          ref={inputRef}
          type="file"
          className="dropzone-input"
          accept={accept}
          onChange={(e) => handleFile(e.target.files[0])}
        />
        {!value ? (
          <>
            <span className="dropzone-icon">{icon}</span>
            <p className="dropzone-text">{label}</p>
            <p className="dropzone-subtext">{subtext}</p>
          </>
        ) : (
          <div className="file-preview">
            <span className="file-preview-icon">{getIcon(value.name)}</span>
            <div>
              <div className="file-preview-name">{value.name}</div>
              <div className="file-preview-size">{formatBytes(value.size)}</div>
            </div>
            <button
              className="file-preview-remove"
              onClick={(e) => { e.stopPropagation(); onChange(null); }}
              title="Remove file"
            >✕</button>
          </div>
        )}
      </div>
    </div>
  );
}
