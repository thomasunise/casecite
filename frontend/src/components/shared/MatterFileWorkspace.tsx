import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Icon } from './Icon';
import { activateOnKey } from './activateOnKey';
import { api } from '../../api';
import { useRagDocsStore } from '../../stores/ragDocsStore';
import { formatFileSize } from '../../utils';
import logger from '../../utils/logger';
import type { DocumentFilter } from '../../types';
import s from './MatterFileWorkspace.module.css';

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

interface MatterFileWorkspaceProps {
  currentFilter: DocumentFilter | null;
  onScopeChange: (filter: DocumentFilter | null) => void;
  /** Open a file in a viewer tab above the workspace. */
  onOpenFile: (docId: string, filename: string) => void;
}

/**
 * The Matter Strategy workspace: the knowledge base rendered as a browsable
 * file system. Clicking a folder scopes the chat to every file in it;
 * clicking a file scopes the chat to that one file; "All documents" resets.
 * The floating conversation dock works over the top of it.
 */
function MatterFileWorkspace({ currentFilter, onScopeChange, onOpenFile }: MatterFileWorkspaceProps) {
  const [tree, setTree] = useState<DocumentTree | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(new Set<string>());
  const [search, setSearch] = useState('');

  const checkedFiles = currentFilter?.document_ids ?? [];
  const checkedFolders = currentFilter?.folder_paths ?? [];
  const totalSelected = checkedFiles.length + checkedFolders.length;
  const allSelected = totalSelected === 0;

  // Emit the union scope; an empty selection means "all documents" (null).
  const emitScope = (ids: string[], paths: string[]) => {
    if (ids.length === 0 && paths.length === 0) {
      onScopeChange(null);
      return;
    }
    onScopeChange({
      document_ids: ids.length ? ids : null,
      folder_paths: paths.length ? paths : null,
      include_subfolders: true,
    });
  };

  const toggleFileCheck = (id: string) => {
    const ids = checkedFiles.includes(id)
      ? checkedFiles.filter((x) => x !== id)
      : [...checkedFiles, id];
    emitScope(ids, checkedFolders);
  };

  const toggleFolderCheck = (path: string) => {
    const paths = checkedFolders.includes(path)
      ? checkedFolders.filter((x) => x !== path)
      : [...checkedFolders, path];
    emitScope(checkedFiles, paths);
  };

  const loadTree = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = (await api.getDocumentTree()) as unknown as DocumentTree;
      setTree(data);
      setExpanded(new Set<string>(data.tree?.map((item) => item.path) || []));
    } catch (e: unknown) {
      logger.error('[MatterFileWorkspace] Error loading tree:', e);
      setError(e instanceof Error ? e.message : 'Failed to load documents');
    }
    setLoading(false);
  }, []);

  // The tree follows the knowledge base live: sidebar uploads refresh the
  // rag-docs store, and any change in the indexed set reloads the tree — no
  // manual Refresh click needed to see a new file.
  const ragInit = useRagDocsStore((st) => st.init);
  const ragDocs = useRagDocsStore((st) => st.ragDocs);
  const ragDocsKey = useMemo(() => ragDocs.map((d) => `${d.id}:${d.status}`).join(','), [ragDocs]);
  useEffect(() => { ragInit(); }, [ragInit]);
  useEffect(() => { loadTree(); }, [loadTree, ragDocsKey]);

  const toggleFolder = (path: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  };

  const renderItem = (item: TreeItem, depth = 0): React.ReactNode => {
    const matches = !search || item.name.toLowerCase().includes(search.toLowerCase());
    const childMatches = item.type === 'folder' && item.children?.some(
      (c) => c.name.toLowerCase().includes(search.toLowerCase()) ||
        (c.type === 'folder' && c.children?.some(
          (cc) => cc.name.toLowerCase().includes(search.toLowerCase())
        ))
    );
    if (search && !matches && !childMatches) return null;

    if (item.type === 'folder') {
      const isOpen = expanded.has(item.path);
      const isChecked = checkedFolders.includes(item.path);
      return (
        <div key={item.path}>
          <div
            className={`${s.row} ${isChecked ? s.rowSelected : ''}`}
            style={{ '--depth-indent': `${depth * 18}px` } as React.CSSProperties}
            role="button"
            tabIndex={0}
            onClick={() => emitScope([], [item.path])}
            onKeyDown={activateOnKey(() => emitScope([], [item.path]))}
          >
            <button
              className={s.chevronBtn}
              onClick={(e) => { e.stopPropagation(); toggleFolder(item.path); }}
              aria-label={isOpen ? 'Collapse folder' : 'Expand folder'}
            >
              <Icon name={isOpen ? 'ChevronDown' : 'ChevronRight'} size={14} />
            </button>
            <span className={s.iconChip}>
              <Icon name={isChecked ? 'FolderOpen' : 'Folder'} size={14} />
            </span>
            <span className={s.folderName}>{item.name}</span>
            <span className={s.meta}>{item.document_count} doc{item.document_count === 1 ? '' : 's'}</span>
            <span className={s.rowSpacer} />
            {isChecked && totalSelected === 1 && (
              <span className={s.scopeBadge}>Chatting with this folder</span>
            )}
            <button
              className={isChecked ? s.checkBtnChecked : s.checkBtn}
              onClick={(e) => { e.stopPropagation(); toggleFolderCheck(item.path); }}
              aria-label={isChecked ? 'Remove folder from selection' : 'Add folder to selection'}
            >
              <Icon name="Check" size={11} />
            </button>
          </div>
          {isOpen && item.children?.map((child) => renderItem(child, depth + 1))}
        </div>
      );
    }

    const isChecked = !!item.id && checkedFiles.includes(item.id);
    return (
      <div
        key={item.id || item.path}
        className={`${s.row} ${isChecked ? s.rowSelected : ''}`}
        style={{ '--depth-indent': `${depth * 18}px` } as React.CSSProperties}
        role="button"
        tabIndex={0}
        onClick={() => item.id && emitScope([item.id], [])}
        onKeyDown={activateOnKey(() => { if (item.id) emitScope([item.id], []); })}
      >
        <span className={s.chevronSpacer} />
        <span className={s.fileIconWrap}>
          <Icon
            name={item.name?.endsWith('.pdf') ? 'FileText' : item.name?.endsWith('.docx') ? 'FileEdit' : 'File'}
            size={15}
            className={s.fileIcon}
          />
        </span>
        <span className={s.name}>{item.name}</span>
        <span className={s.meta}>{item.size ? formatFileSize(item.size) : ''}</span>
        <span className={s.rowSpacer} />
        {isChecked && totalSelected === 1 && (
          <span className={s.scopeBadge}>Chatting with this file</span>
        )}
        {item.id && (
          <button
            className={s.openBtn}
            onClick={(e) => { e.stopPropagation(); onOpenFile(item.id!, item.name); }}
            title="Open file"
            aria-label={`Open ${item.name}`}
          >
            <Icon name="Eye" size={13} />
          </button>
        )}
        {item.id && (
          <button
            className={isChecked ? s.checkBtnChecked : s.checkBtn}
            onClick={(e) => { e.stopPropagation(); toggleFileCheck(item.id!); }}
            aria-label={isChecked ? 'Remove file from selection' : 'Add file to selection'}
          >
            <Icon name="Check" size={11} />
          </button>
        )}
      </div>
    );
  };

  return (
    <div className={s.workspace}>
      <div className={s.toolRow}>
        <span className={s.filesLabel}>
          Files
          <span className={s.filesCount}>{tree?.total_documents ?? 0}</span>
        </span>
        <span className={s.toolSpacer} />
        <div className={s.searchWrap}>
          <Icon name="Search" size={13} className={s.searchIcon} />
          <input
            type="text"
            className={s.searchInput}
            placeholder="Search files…"
            aria-label="Search files"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <button className={s.refreshBtn} onClick={loadTree} disabled={loading} aria-label="Refresh files">
          <Icon name="RefreshCw" size={13} className={loading ? s.spin : undefined} />
        </button>
      </div>

      <div className={s.treeScroll}>
        <div
          className={`${s.row} ${s.allRow} ${allSelected ? s.rowSelected : ''}`}
          role="button"
          tabIndex={0}
          onClick={() => onScopeChange(null)}
          onKeyDown={activateOnKey(() => onScopeChange(null))}
        >
          <span className={s.chevronSpacer} />
          <span className={s.iconChip}>
            <Icon name="Database" size={14} />
          </span>
          <span className={s.folderName}>All documents</span>
          <span className={s.rowSpacer} />
          {allSelected && <span className={s.scopeBadge}>Chatting with everything</span>}
        </div>

        {loading ? (
          <div className={s.stateBox}>
            <Icon name="Loader2" size={22} className={s.spin} />
            <span>Loading your files…</span>
          </div>
        ) : error ? (
          <div className={s.stateBox}>
            <Icon name="AlertCircle" size={20} />
            <span>{error}</span>
            <button className={s.retryBtn} onClick={loadTree}>Retry</button>
          </div>
        ) : (tree?.tree?.length ?? 0) === 0 ? (
          <div className={s.stateBox}>
            <Icon name="FolderX" size={26} />
            <span>No documents yet — add files in the Knowledge Base and they appear here.</span>
          </div>
        ) : (
          tree?.tree?.map((item) => renderItem(item))
        )}
      </div>

      {/* Multi-selection summary — one quiet strip instead of a badge per row */}
      {totalSelected > 1 && (
        <div className={s.scopeBar}>
          <Icon name="MessagesSquare" size={13} />
          <span>
            Chatting with {[
              checkedFiles.length ? `${checkedFiles.length} file${checkedFiles.length === 1 ? '' : 's'}` : null,
              checkedFolders.length ? `${checkedFolders.length} folder${checkedFolders.length === 1 ? '' : 's'}` : null,
            ].filter(Boolean).join(' + ')}
          </span>
          <button className={s.scopeClear} onClick={() => onScopeChange(null)}>
            Clear
          </button>
        </div>
      )}
    </div>
  );
}

export { MatterFileWorkspace };
