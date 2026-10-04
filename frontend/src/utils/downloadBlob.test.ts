import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { downloadBlob } from './downloadBlob';

describe('downloadBlob', () => {
  let createObjectURLMock: ReturnType<typeof vi.fn>;
  let revokeObjectURLMock: ReturnType<typeof vi.fn>;
  let appendChildMock: ReturnType<typeof vi.fn>;
  let removeChildMock: ReturnType<typeof vi.fn>;
  let clickMock: ReturnType<typeof vi.fn>;
  let createdAnchor: Record<string, unknown>;

  beforeEach(() => {
    createObjectURLMock = vi.fn().mockReturnValue('blob:http://localhost/fake-url');
    revokeObjectURLMock = vi.fn();
    clickMock = vi.fn();
    appendChildMock = vi.fn();
    removeChildMock = vi.fn();

    createdAnchor = {
      href: '',
      download: '',
      click: clickMock,
    };

    // Mock only the static methods, not the entire URL constructor
    URL.createObjectURL = createObjectURLMock as unknown as typeof URL.createObjectURL;
    URL.revokeObjectURL = revokeObjectURLMock as unknown as typeof URL.revokeObjectURL;

    vi.spyOn(document, 'createElement').mockReturnValue(createdAnchor as unknown as HTMLElement);
    vi.spyOn(document.body, 'appendChild').mockImplementation(appendChildMock as unknown as <T extends Node>(node: T) => T);
    vi.spyOn(document.body, 'removeChild').mockImplementation(removeChildMock as unknown as <T extends Node>(child: T) => T);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('creates an object URL from the blob', () => {
    const blob = new Blob(['test content'], { type: 'text/plain' });
    downloadBlob(blob, 'test.txt');
    expect(createObjectURLMock).toHaveBeenCalledWith(blob);
  });

  it('sets the download filename on the anchor element', () => {
    const blob = new Blob(['content']);
    downloadBlob(blob, 'report.pdf');
    expect(createdAnchor.download).toBe('report.pdf');
  });

  it('sets the href to the object URL', () => {
    const blob = new Blob(['content']);
    downloadBlob(blob, 'file.txt');
    expect(createdAnchor.href).toBe('blob:http://localhost/fake-url');
  });

  it('appends anchor to body, clicks, removes, and revokes URL', () => {
    const blob = new Blob(['content']);
    downloadBlob(blob, 'file.txt');
    expect(appendChildMock).toHaveBeenCalledWith(createdAnchor);
    expect(clickMock).toHaveBeenCalled();
    expect(removeChildMock).toHaveBeenCalledWith(createdAnchor);
    expect(revokeObjectURLMock).toHaveBeenCalledWith('blob:http://localhost/fake-url');
  });

  it('calls operations in correct order: append, click, remove, revoke', () => {
    const callOrder: string[] = [];
    appendChildMock.mockImplementation(() => callOrder.push('append'));
    clickMock.mockImplementation(() => callOrder.push('click'));
    removeChildMock.mockImplementation(() => callOrder.push('remove'));
    revokeObjectURLMock.mockImplementation(() => callOrder.push('revoke'));

    const blob = new Blob(['content']);
    downloadBlob(blob, 'file.txt');
    expect(callOrder).toEqual(['append', 'click', 'remove', 'revoke']);
  });
});
