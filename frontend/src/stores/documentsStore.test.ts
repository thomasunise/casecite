import { describe, it, expect, beforeEach } from 'vitest';
import { useDocumentsStore } from './documentsStore';

describe('documentsStore', () => {
  beforeEach(() => {
    useDocumentsStore.setState(useDocumentsStore.getInitialState(), true);
  });

  // ==================== Initial State ====================

  it('has correct initial state', () => {
    const state = useDocumentsStore.getState();
    expect(state.documents).toEqual([]);
  });

  // ==================== setDocuments ====================

  it('setDocuments replaces documents with an array', () => {
    const docs = [{ id: '1', name: 'doc1.pdf' }, { id: '2', name: 'doc2.pdf' }];
    useDocumentsStore.getState().setDocuments(docs);
    expect(useDocumentsStore.getState().documents).toEqual(docs);
  });

  it('setDocuments supports functional update', () => {
    useDocumentsStore.setState({ documents: [{ id: '1', name: 'existing.pdf' }] });

    useDocumentsStore.getState().setDocuments((prev) => [
      ...prev,
      { id: '2', name: 'new.pdf' },
    ]);

    expect(useDocumentsStore.getState().documents).toHaveLength(2);
    expect(useDocumentsStore.getState().documents[1]).toEqual({ id: '2', name: 'new.pdf' });
  });

  it('setDocuments can clear all documents', () => {
    useDocumentsStore.setState({ documents: [{ id: '1' }, { id: '2' }] });
    useDocumentsStore.getState().setDocuments([]);
    expect(useDocumentsStore.getState().documents).toEqual([]);
  });

  it('setDocuments functional update can filter documents', () => {
    useDocumentsStore.setState({
      documents: [
        { id: '1', name: 'keep.pdf' },
        { id: '2', name: 'remove.pdf' },
        { id: '3', name: 'keep2.pdf' },
      ],
    });

    useDocumentsStore.getState().setDocuments((prev) =>
      prev.filter((d) => d.name !== 'remove.pdf')
    );

    expect(useDocumentsStore.getState().documents).toHaveLength(2);
    expect(useDocumentsStore.getState().documents.every(d => d.name !== 'remove.pdf')).toBe(true);
  });
});
