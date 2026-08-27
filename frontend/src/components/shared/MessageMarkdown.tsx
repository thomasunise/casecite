import React from 'react';
import s from './MessageMarkdown.module.css';

/** Inline formatting: **bold** becomes real bold; stray markers (single
    asterisks, underscores, backticks) are stripped, never shown raw. */
function renderInline(text: string, keyBase: string): React.ReactNode[] {
  const nodes: React.ReactNode[] = [];
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  parts.forEach((part, i) => {
    if (part.startsWith('**') && part.endsWith('**') && part.length > 4) {
      nodes.push(<strong key={`${keyBase}b${i}`}>{part.slice(2, -2)}</strong>);
    } else if (part) {
      const cleaned = part
        .replace(/`([^`\n]+)`/g, '$1')
        .replace(/\*([^*\n]+)\*/g, '$1')
        .replace(/__([^_\n]+)__/g, '$1')
        .replace(/\b_([^_\n]+)_\b/g, '$1');
      nodes.push(<React.Fragment key={`${keyBase}t${i}`}>{cleaned}</React.Fragment>);
    }
  });
  return nodes;
}

/**
 * The ONE renderer for assistant chat text, shared by every conversation
 * surface — headings, bullets, numbered lists, blockquotes, and bold render
 * as formatting; raw markdown characters never reach the user.
 */
function MessageMarkdown({ text }: { text: string }) {
  const lines = (text || '').split('\n');
  return (
    <div className={s.md}>
      {lines.map((line, i) => {
        const trimmed = line.trim();
        if (!trimmed) return <div key={i} className={s.gap} />;
        const heading = trimmed.match(/^#{1,6}\s+(.*)$/);
        if (heading) {
          return <div key={i} className={s.heading}>{renderInline(heading[1], `l${i}`)}</div>;
        }
        if (/^>\s?/.test(trimmed)) {
          return (
            <blockquote key={i} className={s.quote}>
              {renderInline(trimmed.replace(/^>\s?/, ''), `l${i}`)}
            </blockquote>
          );
        }
        const bullet = trimmed.match(/^[-*•]\s+(.*)$/);
        if (bullet) {
          return (
            <div key={i} className={s.li}>
              <span className={s.marker}>•</span>
              <span className={s.liBody}>{renderInline(bullet[1], `l${i}`)}</span>
            </div>
          );
        }
        const numbered = trimmed.match(/^(\d+)[.)]\s+(.*)$/);
        if (numbered) {
          return (
            <div key={i} className={s.li}>
              <span className={s.marker}>{numbered[1]}.</span>
              <span className={s.liBody}>{renderInline(numbered[2], `l${i}`)}</span>
            </div>
          );
        }
        if (/^(-{3,}|\*{3,}|_{3,})$/.test(trimmed)) {
          return <hr key={i} className={s.rule} />;
        }
        return <p key={i} className={s.p}>{renderInline(trimmed, `l${i}`)}</p>;
      })}
    </div>
  );
}

export { MessageMarkdown };
