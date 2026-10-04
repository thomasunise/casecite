import { useState, useEffect, useId } from 'react';
import { Icon } from './Icon';
import { ModalShell } from './ModalShell';
import { DocumentTreeItemRow } from './DocumentTreeItemRow';
import { api } from '../../api';
import type { DocumentFilter, DocumentTree, DocumentTreeItem } from '../../types';
import s from './DocumentSelector.module.css';
import logger from '../../utils/logger';

interface DocumentSelectorProps {
  isOpen: boolean;
  onClose: () => void;
  onSelect: (filter: DocumentFilter) => void;
  currentFilter: DocumentFilter | null;
}

export const DocumentSelector = ({ isOpen, onClose, onSelect, currentFilter }: DocumentSelectorProps) => {
  const [tree, setTree] = useState<DocumentTree | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedFolders, setExpandedFolders] = useState(new Set<string>());
  const [selectedItems, setSelectedItems] = useState(new Set<string>());
  const [searchFilter, setSearchFilter] = useState('');
  const [selectMode, setSelectMode] = useState('all');
  const titleId = useId();

  useEffect(() => {
    if (isOpen) {
      loadTree();
      const initialItems = new Set<string>();
      if (currentFilter?.document_ids) {
        currentFilter.document_ids.forEach((id: string) => initialItems.add(id));
      }
      if (currentFilter?.folder_paths) {
        currentFilter.folder_paths.forEach((path: string) => initialItems.add(path));
      }
      setSelectedItems(initialItems);

      if (currentFilter?.search_all || initialItems.size === 0) {
        setSelectMode('all');
      } else {
        setSelectMode('mixed');
      }
    }
  }, [isOpen, currentFilter]);

  const loadTree = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getDocumentTree() as unknown as DocumentTree;
      setTree(data);
      const firstLevel = new Set(data.tree.map((item: DocumentTreeItem) => item.path));
      setExpandedFolders(firstLevel);
    } catch (e: unknown) {
      logger.error('[DocSelector] Error loading tree:', e);
      setError(e instanceof Error ? e.message : String(e));
    }
    setLoading(false);
  };

  const toggleFolder = (path: string) => {
    setExpandedFolders(prev => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  };

  const toggleSelect = (item: DocumentTreeItem) => {
    setSelectedItems(prev => {
      const next = new Set(prev);
      const key = item.type === 'folder' ? item.path : item.id;
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
    if (selectMode === 'all') {
      setSelectMode(item.type === 'folder' ? 'folders' : 'files');
    } else if (item.type === 'folder' && selectMode === 'files') {
      setSelectMode('mixed');
    } else if (item.type === 'file' && selectMode === 'folders') {
      setSelectMode('mixed');
    }
  };

  const selectAll = () => {
    setSelectedItems(new Set());
    setSelectMode('all');
  };

  const clearSelection = () => {
    setSelectedItems(new Set());
  };

  const handleApply = () => {
    if (selectMode === 'all' || selectedItems.size === 0) {
      onSelect({ search_all: true });
    } else {
      const folderPaths: string[] = [];
      const documentIds: string[] = [];
      selectedItems.forEach((item: string) => {
        if (item.startsWith('/')) {
          folderPaths.push(item);
        } else {
          documentIds.push(item);
        }
      });

      const filter: DocumentFilter = {};
      if (folderPaths.length > 0) filter.folder_paths = folderPaths;
      if (documentIds.length > 0) filter.document_ids = documentIds;
      filter.include_subfolders = true;

      onSelect(filter);
    }
    onClose();
  };

  if (!isOpen) return null;

  return (
    <ModalShell onClose={onClose} overlayClassName={s.overlay} className={s.container} labelledBy={titleId}>
        {/* Header */}
        <div className={s.header}>
          <div className={s.headerRow}>
            <div className={s.headerIcon}>
              <Icon name="FolderSearch" size={20} className={s.iconWhite} />
            </div>
            <div>
              <h2 id={titleId} className={s.headerTitle}>Select Documents</h2>
              <p className={s.headerSubtitle}>Choose which documents to include in your search</p>
            </div>
            <button onClick={onClose} className={s.closeBtn} aria-label="Close">
              <Icon name="X" size={20} className={s.iconGray500} />
            </button>
          </div>

          {/* Quick Actions */}
          <div className={s.quickActions}>
            <button
              onClick={selectAll}
              className={`${s.quickActionBtn} ${selectMode === 'all' ? s.quickActionBtnActive : ''}`}
            >
              <Icon name="Database" size={14} />
              All Documents
            </button>
            <button
              onClick={clearSelection}
              className={s.quickActionBtn}
            >
              <Icon name="XCircle" size={14} />
              Clear Selection
            </button>
          </div>

          {/* Search */}
          <div className={s.searchWrapper}>
            <Icon name="Search" size={16} className={s.searchIcon} />
            <input
              type="text"
              placeholder="Search folders and files..."
              aria-label="Search folders and files"
              value={searchFilter}
              onChange={e => setSearchFilter(e.target.value)}
              className={s.searchInput}
            />
          </div>
        </div>

        {/* Tree Content */}
        <div className={s.treeContent}>
          {loading ? (
            <div className={s.loadingState}>
              <Icon name="Loader2" size={32} className={s.spinnerGold} />
              <p>Loading document tree...</p>
            </div>
          ) : error ? (
            <div className={s.errorState}>
              <Icon name="AlertCircle" size={32} />
              <p>{error}</p>
              <button onClick={loadTree} className={s.retryBtn}>
                Retry
              </button>
            </div>
          ) : tree?.tree?.length === 0 ? (
            <div className={s.emptyState}>
              <Icon name="FolderX" size={48} className={s.iconGray300} />
              <p>No documents indexed</p>
              <p>
                Upload documents using the <strong>paperclip button</strong> or connect a cloud storage provider in Settings.
              </p>
              <div className={s.emptyTip}>
                <strong>Tip:</strong> After uploading, wait for indexing to complete. Check the Documents panel to see status.
              </div>
            </div>
          ) : (
            <div>
              {tree?.tree?.map((item: DocumentTreeItem) => (
                <DocumentTreeItemRow
                  key={item.id || item.path}
                  s={s}
                  item={item}
                  depth={0}
                  expandedFolders={expandedFolders}
                  selectedItems={selectedItems}
                  searchFilter={searchFilter}
                  toggleFolder={toggleFolder}
                  toggleSelect={toggleSelect}
                />
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className={s.footer}>
          <div className={s.footerInfo}>
            {selectMode === 'all'
              ? `Searching all ${tree?.total_documents || 0} documents`
              : `${selectedItems.size} item${selectedItems.size === 1 ? '' : 's'} selected`
            }
          </div>
          <div className={s.footerActions}>
            <button
              onClick={onClose}
              className={s.cancelBtn}
            >
              Cancel
            </button>
            <button
              onClick={handleApply}
              className={s.applyBtn}
            >
              Apply Filter
            </button>
          </div>
        </div>
    </ModalShell>
  );
};
