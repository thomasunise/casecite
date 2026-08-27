import React, { useState } from 'react';
import { Icon } from './Icon';
import s from './PdfDocumentViewer.module.css';

interface PdfDocumentViewerProps {
  fileUrl: string;
  wordCount?: number;
}

export const PdfDocumentViewer: React.FC<PdfDocumentViewerProps> = ({ fileUrl, wordCount }) => {
  const [loadError, setLoadError] = useState(false);

  // Hide thumbnail sidebar, fit document to width
  const iframeSrc = `${fileUrl}#navpanes=0&view=FitH`;

  return (
    <div className={s.pdfViewer}>
      {/* Info bar */}
      <div className={s.pdfToolbar}>
        <Icon name="FileText" size={13} className={s.iconGray400} />
        <span className={s.pdfInfoLabel}>Document Preview</span>
        {wordCount != null && (
          <span className={s.pdfPageCount}>
            {wordCount.toLocaleString()} words (extracted)
          </span>
        )}
      </div>

      {/* PDF rendering area — native browser PDF viewer */}
      <div className={s.pdfScrollArea}>
        {loadError ? (
          <div className={s.pdfError}>
            <Icon name="AlertTriangle" size={32} />
            <span>Failed to render PDF</span>
            <span className={s.pdfErrorDetail}>
              Your browser may not support inline PDF viewing.
              <a href={fileUrl} download className={s.pdfDownloadLink}>Download the file</a>
            </span>
          </div>
        ) : (
          <iframe
            src={iframeSrc}
            className={s.pdfIframe}
            title="Document viewer"
            onError={() => setLoadError(true)}
          />
        )}
      </div>
    </div>
  );
};
