import React, { useState, useEffect } from 'react';
import { Icon } from './Icon';
import { formatFileSize } from '../../utils';
import { api } from '../../api';
import s from './ContractFilePicker.module.css';
import logger from '../../utils/logger';

interface TreeItem {
  id?: string;
  name: string;
  path: string;
  type: 'file' | 'folder';
  size?: number;
  document_count?: number;
  children?: TreeItem[];
}

interface DocumentTree {
  tree?: TreeItem[];
  total_documents?: number;
  [key: string]: unknown;
}

interface ContractFilePickerProps {
  isOpen: boolean;
  onClose: () => void;
  /** Ordered selection: 1 file opens the normal viewer; 2-4 open split panes. */
  onSelect: (docs: Array<{ id: string; name: string }>) => void;
  loading?: boolean;
  /** Context overrides (e.g. the Drafting reference picker). */
  subtitle?: string;
  confirmLabel?: (count: number) => string;
  multiHint?: string;
}

const MAX_SELECT = 4;

export const ContractFilePicker = ({
  isOpen, onClose, onSelect, loading, subtitle, confirmLabel, multiHint,
}: ContractFilePickerProps) => {
  const [tree, setTree] = useState<DocumentTree | null>(null);
  const [treeLoading, setTreeLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedFolders, setExpandedFolders] = useState(new Set<string>());
  const [selected, setSelected] = useState<Array<{ id: string; name: string }>>([]);
  const [searchFilter, setSearchFilter] = useState('');

  useEffect(() => {
    if (isOpen) {
      loadTree();
      setSelected([]);
      setSearchFilter('');
    }
  }, [isOpen]);

  const loadTree = async () => {
    setTreeLoading(true);
    setError(null);
    try {
      const data = await api.getDocumentTree() as unknown as DocumentTree;
      setTree(data);
      const firstLevel = new Set<string>(data.tree?.map((item: TreeItem) => item.path) || []);
      setExpandedFolders(firstLevel);
    } catch (e: unknown) {
      logger.error('[ContractFilePicker] Error loading tree:', e);
      setError(e instanceof Error ? e.message : 'Failed to load documents');
    }
    setTreeLoading(false);
  };

  const toggleFolder = (path: string) => {
    setExpandedFolders(prev => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  };

  // Click toggles a file in/out of the ordered selection (max 4). The first
  // pick is the primary contract; extra picks open as split panes.
  const toggleFile = (item: TreeItem) => {
    if (!item.id) return;
    setSelected((prev) => {
      if (prev.some((d) => d.id === item.id)) return prev.filter((d) => d.id !== item.id);
      if (prev.length >= MAX_SELECT) return prev;
      return [...prev, { id: item.id!, name: item.name }];
    });
  };

  const handleLoad = () => {
    if (selected.length > 0) onSelect(selected);
  };

  const renderTreeItem = (item: TreeItem, depth = 0): React.ReactNode => {
    const isExpanded = expandedFolders.has(item.path);
    const matchesSearch = !searchFilter ||
      item.name.toLowerCase().includes(searchFilter.toLowerCase());

    const hasMatchingChildren = item.type === 'folder' && item.children?.some(
      (child: TreeItem) => child.name.toLowerCase().includes(searchFilter.toLowerCase()) ||
      (child.type === 'folder' && child.children?.some((c: TreeItem) =>
        c.name.toLowerCase().includes(searchFilter.toLowerCase())
      ))
    );

    if (searchFilter && !matchesSearch && !hasMatchingChildren) return null;

    if (item.type === 'folder') {
      return (
        <div key={item.path}>
          <div
            className={`${s.treeItem} ${s.treeItemIndent}`}
            style={{ '--depth-indent': `${depth * 20}px` } as React.CSSProperties}
            onClick={() => toggleFolder(item.path)}
          >
            <span className={s.folderToggle}>
              <Icon name={isExpanded ? 'ChevronDown' : 'ChevronRight'} size={16} className={s.iconGray500} />
            </span>
            <Icon name="Folder" size={18} style={{ color: isExpanded ? 'var(--gold-500)' : 'var(--gray-500)' }} />
            <span className={s.folderName}>{item.name}</span>
            <span className={s.docCount}>{item.document_count} docs</span>
          </div>
          {isExpanded && item.children?.map((child: TreeItem) => renderTreeItem(child, depth + 1))}
        </div>
      );
    }

    // File item
    const selectionIndex = selected.findIndex((d) => d.id === item.id);
    const isActive = selectionIndex !== -1;
    return (
      <div key={item.id}>
        <div
          className={`${s.treeItem} ${s.treeItemIndent} ${isActive ? s.treeItemActive : ''}`}
          style={{ '--depth-indent': `${depth * 20}px` } as React.CSSProperties}
          onClick={() => toggleFile(item)}
          onDoubleClick={() => { if (item.id) onSelect([{ id: item.id, name: item.name }]); }}
        >
          <span className={s.fileSpacer} />
          <span className={`${s.selectMark} ${isActive ? s.selectMarkActive : ''}`}>
            {isActive ? selectionIndex + 1 : ''}
          </span>
          <Icon
            name={item.name?.endsWith('.pdf') ? 'FileText' : item.name?.endsWith('.docx') ? 'FileEdit' : 'File'}
            size={16}
            style={{ color: isActive ? 'var(--gold-600)' : 'var(--gray-500)' }}
          />
          <span className={s.fileName}>{item.name}</span>
          <span className={s.fileMeta}>
            {item.size ? formatFileSize(item.size) : null}
          </span>
        </div>
      </div>
    );
  };

  if (!isOpen) return null;

  return (
    <div className={s.overlay} onClick={onClose}>
      <div className={s.container} onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className={s.header}>
          <div className={s.headerRow}>
            <div className={s.headerIcon}>
              <Icon name="FolderSearch" size={20} className={s.iconWhite} />
            </div>
            <div>
              <h2 className={s.headerTitle}>Browse Documents</h2>
              <p className={s.headerSubtitle}>
                {subtitle || `Pick one document to analyze — or up to ${MAX_SELECT} to open side by side and compare`}
              </p>
            </div>
            <button onClick={onClose} className={s.closeBtn} aria-label="Close document browser">
              <Icon name="X" size={20} className={s.iconGray500} />
            </button>
          </div>

          <div className={s.searchWrapper}>
            <Icon name="Search" size={16} className={s.searchIcon} />
            <input
              aria-label="Search files"
              type="text"
              placeholder="Search files..."
              value={searchFilter}
              onChange={e => setSearchFilter(e.target.value)}
              className={s.searchInput}
            />
          </div>
        </div>

        {/* Tree Content */}
        <div className={s.treeContent}>
          {treeLoading ? (
            <div className={s.loadingState}>
              <Icon name="Loader2" size={32} className={s.spinnerGold} />
              <p>Loading documents...</p>
            </div>
          ) : error ? (
            <div className={s.errorState}>
              <Icon name="AlertCircle" size={32} />
              <p>{error}</p>
              <button onClick={loadTree} className={s.retryBtn}>Retry</button>
            </div>
          ) : tree?.tree?.length === 0 ? (
            <div className={s.emptyState}>
              <Icon name="FolderX" size={48} className={s.iconGray300} />
              <p>No documents indexed</p>
              <p>Upload documents first using the upload button in the toolbar.</p>
            </div>
          ) : (
            <div>
              {tree?.tree?.map((item: TreeItem) => renderTreeItem(item))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className={s.footer}>
          <div className={s.footerInfo}>
            {selected.length === 0
              ? `${tree?.total_documents || 0} documents available`
              : selected.length === 1
                ? `Selected: ${selected[0].name}`
                : `${selected.length} of ${MAX_SELECT} selected${multiHint ?? " — they'll open side by side"}`
            }
          </div>
          <div className={s.footerActions}>
            <button onClick={onClose} className={s.cancelBtn}>Cancel</button>
            <button
              onClick={handleLoad}
              disabled={selected.length === 0 || loading}
              className={s.loadBtn}
            >
              {loading
                ? <><Icon name="Loader2" size={16} className={s.spinner} /> Loading...</>
                : confirmLabel
                  ? confirmLabel(selected.length)
                : selected.length > 1
                  ? `Open ${selected.length} side by side`
                  : 'Load Document'
              }
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
