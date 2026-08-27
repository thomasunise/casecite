import { useEffect, useRef, useState } from 'react';
import { api } from '../../api';
import { Icon } from './Icon';
import s from './OpinionAnchorView.module.css';

function findRange(haystack: string, needle: string): [number, number] | null {
  if (!haystack || !needle) return null;
  const idx = haystack.indexOf(needle);
  if (idx >= 0) return [idx, idx + needle.length];
  const norm = needle.replace(/\s+/g, ' ').trim();
  if (norm.length < 12) return null;
  const pattern = norm.split(' ').map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('\\s+');
  try {
    const m = new RegExp(pattern).exec(haystack);
    if (m) return [m.index, m.index + m[0].length];
  } catch { /* invalid regex */ }
  return null;
}

interface OpinionAnchorViewProps {
  opinionId: string;
  passage: string;
  onOpenFull?: () => void;
}

export function OpinionAnchorView({ opinionId, passage, onOpenFull }: OpinionAnchorViewProps) {
  const [text, setText] = useState<string | null>(null);
  const [caseName, setCaseName] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const markRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setText(null);
    api.getCaseOpinion(opinionId)
      .then((data) => {
        if (cancelled) return;
        const body = (data.opinion_text || data.syllabus || '') as string;
        setCaseName((data.case_name as string) || '');
        setText(body || '');
        if (!body) setError('No opinion text available for this case.');
        setLoading(false);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : 'Failed to load opinion.');
        setLoading(false);
      });
    return () => { cancelled = true; };
  }, [opinionId]);

  const range = text ? findRange(text, passage) : null;

  useEffect(() => {
    if (text && range && markRef.current) {
      markRef.current.scrollIntoView({ block: 'center' });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text]);

  return (
    <div className={s.wrap}>
      {loading && <div className={s.state}><Icon name="Loader2" size={18} className={s.spin} /> Loading the opinion…</div>}
      {error && <div className={s.error}><Icon name="AlertCircle" size={14} /> {error}</div>}
      {text && (
        <>
          <div className={s.head}>
            <span className={s.caseName}>{caseName || 'Opinion'}</span>
            <span className={range ? s.foundBadge : s.notFoundBadge}>
              <Icon name={range ? 'ShieldCheck' : 'ShieldAlert'} size={12} />
              {range ? 'Passage located in opinion' : 'Passage not located — verify manually'}
            </span>
            {onOpenFull && (
              <button className={s.fullBtn} onClick={onOpenFull}>
                <Icon name="Maximize2" size={12} /> Open full case
              </button>
            )}
          </div>
          <div className={s.opinion}>
            {range ? (
              <>
                {text.slice(0, range[0])}
                <span ref={markRef} className={s.mark}>{text.slice(range[0], range[1])}</span>
                {text.slice(range[1])}
              </>
            ) : text}
          </div>
        </>
      )}
    </div>
  );
}
