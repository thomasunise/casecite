import { useId } from 'react';
import { useConnectorsStore } from '../../stores/connectorsStore';
import s from './FilePickerModal.module.css';
import { Icon } from '../shared/Icon';
import { ModalShell } from '../shared/ModalShell';

function ProvidersModal() {
  const { showProvidersModal, setShowProvidersModal } = useConnectorsStore();
  const titleId = useId();

  if (!showProvidersModal) return null;

  return (
    <ModalShell onClose={() => setShowProvidersModal(false)} overlayClassName={s.modalOverlay} className={s.modalContainerProviders} labelledBy={titleId}>
        <div className={s.modalHeader}>
          <div className={s.modalHeaderLeft}>
            <div className={s.modalIconProviders}>
              <Icon name="Link" size={20} className={s.iconGold500} />
            </div>
            <div>
              <h2 id={titleId} className={s.modalTitle}>Additional Integrations</h2>
              <p className={s.modalSubtitle}>Enterprise document management & practice management</p>
            </div>
          </div>
          <button className={s.modalClose} onClick={() => setShowProvidersModal(false)} aria-label="Close">
            <Icon name="X" size={20} />
          </button>
        </div>
        <div className={s.providersBody}>
          {/* Enterprise DMS */}
          <div className={s.sectionGroup}>
            <div className={s.sectionLabel}>Document Management Systems</div>
            <div className={s.integrationList}>
              {[
                { name: 'NetDocuments', icon: 'FileStack', color: '#1E88E5', desc: 'Full document sync and search' },
                { name: 'iManage', icon: 'Database', color: '#6366F1', desc: 'Work product management integration' },
              ].map(p => (
                <div key={p.name} className={s.integrationCard}>
                  <div className={s.integrationCardIcon} style={{background: p.color}}>
                    <Icon name={p.icon} size={18} className={s.iconWhite} />
                  </div>
                  <div className={s.integrationCardInfo}>
                    <div className={s.integrationCardName}>{p.name}</div>
                    <div className={s.integrationCardDesc}>{p.desc}</div>
                  </div>
                  <span className={s.privateInstallBadge}>Private Install</span>
                </div>
              ))}
            </div>
          </div>

          {/* Practice Management */}
          <div className={s.sectionGroup}>
            <div className={s.sectionLabel}>Practice Management</div>
            <div className={s.integrationList}>
              {[
                { name: 'Clio', icon: 'Scale', color: '#2563EB', desc: 'Time tracking & billing sync' },
                { name: 'Filevine', icon: 'FolderTree', color: '#10B981', desc: 'Case management integration' },
              ].map(p => (
                <div key={p.name} className={s.integrationCard}>
                  <div className={s.integrationCardIcon} style={{background: p.color}}>
                    <Icon name={p.icon} size={18} className={s.iconWhite} />
                  </div>
                  <div className={s.integrationCardInfo}>
                    <div className={s.integrationCardName}>{p.name}</div>
                    <div className={s.integrationCardDesc}>{p.desc}</div>
                  </div>
                  <span className={s.privateInstallBadge}>Private Install</span>
                </div>
              ))}
            </div>
          </div>

          {/* Full sync for picker providers */}
          <div className={s.sectionGroup}>
            <div className={s.sectionLabel}>Full Sync Access</div>
            <div className={s.integrationList}>
              {[
                { name: 'Google Drive', icon: 'HardDrive', color: '#4285F4', desc: 'Automatic background sync of entire folders' },
                { name: 'OneDrive & SharePoint', icon: 'Cloud', color: '#0078D4', desc: 'Continuous sync via Microsoft Graph API' },
                { name: 'Box', icon: 'Box', color: '#0061D5', desc: 'Enterprise content management sync' },
                { name: 'Dropbox', icon: 'Droplet', color: '#0061FF', desc: 'Automatic folder monitoring and sync' },
              ].map(p => (
                <div key={p.name} className={s.integrationCard}>
                  <div className={s.integrationCardIcon} style={{background: p.color}}>
                    <Icon name={p.icon} size={18} className={s.iconWhite} />
                  </div>
                  <div className={s.integrationCardInfo}>
                    <div className={s.integrationCardName}>{p.name}</div>
                    <div className={s.integrationCardDesc}>{p.desc}</div>
                  </div>
                  <span className={s.privateInstallBadge}>Private Install</span>
                </div>
              ))}
            </div>
          </div>

          {/* Explanation */}
          <div className={s.infoBox}>
            <div className={s.infoBoxContent}>
              <Icon name="Shield" size={18} className={s.infoIconBlue} />
              <div>
                <div className={s.infoBoxTitle}>Private Install Required</div>
                <div className={s.infoBoxText}>
                  These integrations require authenticated access to your organization's systems. With a <strong>Private Install</strong>, your IT team configures secure credentials within your own infrastructure — giving you full sync access, automatic document monitoring, and enterprise DMS connectivity while maintaining complete control over your data.
                </div>
              </div>
            </div>
          </div>
        </div>
    </ModalShell>
  );
}

export { ProvidersModal };
export default ProvidersModal;
