import '../styles/components.css';

const STEPS_DEFAULT = [
  'Uploading documents...',
  'Extracting text content...',
  'Analyzing with AI...',
  'Building intelligence brief...',
];

export default function LoadingOverlay({ title = 'Processing...', message = '', steps = STEPS_DEFAULT, currentStep = -1 }) {
  return (
    <div className="loading-overlay">
      <div className="loading-card">
        <div className="loading-spinner-wrapper">
          <div className="loading-ring" />
          <div className="loading-ring-2" />
        </div>
        <div className="loading-title">{title}</div>
        {message && <div className="loading-message">{message}</div>}
        {steps.length > 0 && (
          <div className="loading-steps">
            {steps.map((step, i) => (
              <div key={i} className={`loading-step ${currentStep > i ? 'done' : ''}`}>
                <div className="step-icon">
                  {currentStep > i ? '✓' : i + 1}
                </div>
                <span>{step}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
