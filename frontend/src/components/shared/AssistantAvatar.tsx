import s from './AssistantAvatar.module.css';

/** The CaseCite star — the ONE assistant identity in every conversation.
    Views keep their own avatar box; this is the glyph inside it. */
function AssistantAvatar() {
  return <span className={s.star} aria-hidden="true">*</span>;
}

export { AssistantAvatar };
