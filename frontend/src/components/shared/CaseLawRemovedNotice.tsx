import { Icon } from './Icon';
import s from './CaseLawRemovedNotice.module.css';

interface CaseLawRemovedNoticeProps {
  /** Case references the server removed because they could not be verified. */
  removed?: string[] | null;
  className?: string;
}

/**
 * Says plainly that the server took unverifiable case references out of a
 * generated answer, draft or brief, and lists them. Renders nothing when the
 * server removed none.
 */
export function CaseLawRemovedNotice({ removed, className }: CaseLawRemovedNoticeProps) {
  if (!removed?.length) return null;
  const n = removed.length;
  return (
    <div role="note" className={className ?? s.notice}>
      <Icon name="ShieldAlert" size={12} className={s.icon} />
      <div>
        {n} case reference{n === 1 ? '' : 's'} could not be verified against a real source and{' '}
        {n === 1 ? 'was' : 'were'} removed:
        <ul className={s.list}>
          {removed.map((name, i) => <li key={`${name}-${i}`}>{name}</li>)}
        </ul>
      </div>
    </div>
  );
}
