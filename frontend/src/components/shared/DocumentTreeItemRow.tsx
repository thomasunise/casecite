import React from 'react';
import { Icon } from './Icon';
import { activateOnKey } from './activateOnKey';
import { formatFileSize } from '../../utils';
import type { DocumentTreeItem } from '../../types';
import localStyles from './DocumentTreeItemRow.module.css';

interface DocumentTreeItemRowProps {
  s: Record<string, string>;
  item: DocumentTreeItem;
  depth: number;
  expandedFolders: Set<string>;
  selectedItems: Set<string>;
  searchFilter: string;
  toggleFolder: (path: string) => void;
  toggleSelect: (item: DocumentTreeItem) => void;
}

function DocumentTreeItemRow({ s, item, depth, expandedFolders, selectedItems, searchFilter, toggleFolder, toggleSelect }: DocumentTreeItemRowProps) {
  const isExpanded = expandedFolders.has(item.path);
  const isSelected = selectedItems.has(item.type === 'folder' ? item.path : item.id);
  const matchesSearch = !searchFilter ||
    item.name.toLowerCase().includes(searchFilter.toLowerCase());

  const hasMatchingChildren = item.type === 'folder' && item.children?.some(
    (child: DocumentTreeItem) => child.name.toLowerCase().includes(searchFilter.toLowerCase()) ||
    (child.type === 'folder' && child.children?.some((c: DocumentTreeItem) =>
      c.name.toLowerCase().includes(searchFilter.toLowerCase())
    ))
  );

  if (searchFilter && !matchesSearch && !hasMatchingChildren) return null;

  return (
    <div>
      <div
        className={`${s.treeItem} ${localStyles.treeItemIndent} ${isSelected ? s.treeItemSelected : ''}`}
        style={{ '--depth-indent': `${depth * 20}px` } as React.CSSProperties}
      >
        {item.type === 'folder' ? (
          <>
            <span
              role="button"
              tabIndex={0}
              aria-label={isExpanded ? `Collapse ${item.name}` : `Expand ${item.name}`}
              aria-expanded={isExpanded}
              onClick={() => toggleFolder(item.path)}
              onKeyDown={activateOnKey(() => toggleFolder(item.path))}
              className={s.folderToggle}
            >
              <Icon name={isExpanded ? 'ChevronDown' : 'ChevronRight'} size={16} className={s.iconGray500} />
            </span>
            <input
              aria-label={`Select folder ${item.name}`}
              type="checkbox"
              checked={isSelected}
              onChange={() => toggleSelect(item)}
              className={s.checkbox}
            />
            <Icon name="Folder" size={18} style={{color: isExpanded ? 'var(--gold-500)' : 'var(--gray-500)'}} />
            <span className={s.folderName}>{item.name}</span>
            <span className={s.docCount}>
              {item.document_count} docs
            </span>
          </>
        ) : (
          <>
            <span className={s.fileSpacer} />
            <input
              aria-label={`Select ${item.name}`}
              type="checkbox"
              checked={isSelected}
              onChange={() => toggleSelect(item)}
              className={s.checkbox}
            />
            <Icon
              name={item.name.endsWith('.pdf') ? 'FileText' : item.name.endsWith('.docx') ? 'FileEdit' : 'File'}
              size={16}
              className={s.iconGray500}
            />
            <span className={s.fileName}>
              {item.name}
            </span>
            {item.size && (
              <span className={s.fileSize}>
                {formatFileSize(item.size)}
              </span>
            )}
          </>
        )}
      </div>
      {item.type === 'folder' && isExpanded && item.children?.map((child: DocumentTreeItem) => (
        <DocumentTreeItemRow
          key={child.id || child.path}
          s={s}
          item={child}
          depth={depth + 1}
          expandedFolders={expandedFolders}
          selectedItems={selectedItems}
          searchFilter={searchFilter}
          toggleFolder={toggleFolder}
          toggleSelect={toggleSelect}
        />
      ))}
    </div>
  );
}

export { DocumentTreeItemRow };
