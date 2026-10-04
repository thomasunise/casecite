import { useId } from 'react';
import { useConnectorsStore } from '../../stores/connectorsStore';
import s from './FilePickerModal.module.css';
import { Icon } from '../shared/Icon';
import { ModalShell } from '../shared/ModalShell';

function FilePickerModal() {
  const titleId = useId();
  const {
    showPickerModal, setShowPickerModal,
    activePickerProvider, connectors,
    pickerLoading, openActivePicker,
  } = useConnectorsStore();

  if (!showPickerModal) return null;

  const provider = connectors.find((c: { id: string }) => c.id === activePickerProvider);

  return (
    <ModalShell onClose={() => setShowPickerModal(false)} overlayClassName={s.modalOverlay} className={s.modalContainerPicker} labelledBy={titleId}>
        <div className={s.modalHeader}>
          <div className={s.modalHeaderLeft}>
            <div className={s.modalIcon} style={{background: provider?.color || 'var(--navy-800)'}}>
              <Icon name={provider?.icon || 'Cloud'} size={20} className={s.iconWhite} />
            </div>
            <div>
              <h2 id={titleId} className={s.modalTitle}>Import from {provider?.name}</h2>
              <p className={s.modalSubtitle}>Select files to import</p>
            </div>
          </div>
          <button className={s.modalClose} onClick={() => setShowPickerModal(false)} aria-label="Close">
            <Icon name="X" size={20} />
          </button>
        </div>
        <div className={s.pickerBody}>
          <div className={s.pickerInfoBox}>
            <div className={s.pickerInfoContent}>
              <Icon name="Upload" size={20} className={s.infoIconBlue} />
              <div>
                <div className={s.pickerInfoTitle}>Select files to import</div>
                <div className={s.pickerInfoText}>
                  Browse your {provider?.name} and select documents to import. Supported formats: PDF, Word, TXT, RTF.
                </div>
              </div>
            </div>
          </div>

          <button
            onClick={openActivePicker}
            disabled={pickerLoading}
            className={s.browseBtn}
            style={{
              background: provider?.color || 'var(--navy-700)',
              opacity: pickerLoading ? 0.7 : 1,
            }}
          >
            {pickerLoading ? (
              <>
                <Icon name="Loader2" size={18} className={s.spinnerIcon} />
                Opening {provider?.name}...
              </>
            ) : (
              <>
                <Icon name="FolderOpen" size={18} />
                Browse {provider?.name}
              </>
            )}
          </button>

          <div className={s.pickerDisclaimer}>
            Your files are imported directly — nothing is stored on third-party servers.
          </div>
        </div>
    </ModalShell>
  );
}

export { FilePickerModal };
export default FilePickerModal;
