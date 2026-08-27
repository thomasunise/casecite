import { useId } from 'react';
import s from './AppModals.module.css';
import { ModalShell } from '../components/shared/ModalShell';
import { useUIStore } from '../stores/uiStore';
import { useSettingsStore } from '../stores/settingsStore';
import { useCaseComparisonStore } from '../stores/caseComparisonStore';
import { useResearch } from '../contexts/ResearchContext';
import {
  Icon,
  CitationModal,
  DocumentSelector,
  RAGSettingsModal,
  CaseComparisonModal,
  ShortcutsHelp,
  LoginModal,
  SignupModal,
  ForgotPasswordModal,
  MfaChallengeModal,
  FilePickerModal,
  ProvidersModal,
} from '../components';

export function AppModals() {
  const { showSettings, setShowSettings, showShortcutsHelp, setShowShortcutsHelp, addToast, previewModal, setPreviewModal } = useUIStore();
  const { ragSettings, handleSaveSettings } = useSettingsStore();
  const { showCaseComparison, setShowCaseComparison, caseComparisonData, caseComparisonLoading, showCompareDocSelector, setShowCompareDocSelector, setPendingCompareCase, executeComparison, compareDocFilter } = useCaseComparisonStore();
  const { selectedCitation, setSelectedCitation, handleCitationUpdate } = useResearch();
  const previewTitleId = useId();
  const closePreview = () => setPreviewModal({ show: false, title: '', content: '' });

  return (
    <>
      <RAGSettingsModal isOpen={showSettings} onClose={() => setShowSettings(false)} settings={ragSettings} onSave={handleSaveSettings} />
      <CitationModal isOpen={!!selectedCitation} onClose={() => setSelectedCitation(null)} citation={selectedCitation} onUpdateStatus={handleCitationUpdate} />
      <CaseComparisonModal isOpen={showCaseComparison} onClose={() => setShowCaseComparison(false)} data={caseComparisonData} loading={caseComparisonLoading} />
      <ShortcutsHelp isOpen={showShortcutsHelp} onClose={() => setShowShortcutsHelp(false)} />

      <FilePickerModal />
      <ProvidersModal />

      <DocumentSelector
        isOpen={showCompareDocSelector}
        onClose={() => { setShowCompareDocSelector(false); setPendingCompareCase(null); }}
        onSelect={executeComparison}
        currentFilter={compareDocFilter}
      />

      <LoginModal />
      <SignupModal />
      <ForgotPasswordModal />
      <MfaChallengeModal />

      {/* Preview Modal */}
      <ModalShell
        isOpen={previewModal.show}
        onClose={closePreview}
        overlayClassName={s.overlay}
        className={s.panel}
        labelledBy={previewTitleId}
        overlayProps={{ 'data-modal': 'preview' }}
      >
            <div className={s.header}>
              <div className={s.headerLeft}>
                <div className={s.iconBadge}>
                  <Icon name="FileText" size={20} className={s.previewFileIcon} />
                </div>
                <div>
                  <h2 id={previewTitleId} className={s.title}>{previewModal.title}</h2>
                  <p className={s.subtitle}>Document Preview</p>
                </div>
              </div>
              <div className={s.headerActions}>
                <button
                  className={s.copyBtn}
                  onClick={() => { navigator.clipboard.writeText(previewModal.content); addToast('Copied to clipboard', 'success'); }}
                >
                  <Icon name="Copy" size={14} /> Copy
                </button>
                <button
                  className={s.closeIconBtn}
                  onClick={closePreview}
                  aria-label="Close"
                >
                  <Icon name="X" size={20} className={s.closeXIcon} />
                </button>
              </div>
            </div>
            <div className={s.body}>
              {previewModal.content}
            </div>
            <div className={s.footer}>
              <button
                className={s.closeBtn}
                onClick={closePreview}
              >
                Close
              </button>
            </div>
      </ModalShell>
    </>
  );
}
