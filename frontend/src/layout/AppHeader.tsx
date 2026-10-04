import { useSettingsStore } from '../stores/settingsStore';
import { useAuthStore } from '../stores/authStore';
import { useUIStore } from '../stores/uiStore';
import { Icon } from '../components';
import s from './AppHeader.module.css';

export function AppHeader() {
  const { systemStats } = useSettingsStore();
  const { isAuthenticated, user, handleLogin, handleShowSignup, handleLogout } = useAuthStore();
  const { setShowSettings, leftSidebarOpen, setLeftSidebarOpen, rightPanelOpen, setRightPanelOpen } = useUIStore();

  // Three states: a failed or unanswered health check must never read as green.
  const health = systemStats.isHealthy === null ? 'unknown' : systemStats.isHealthy ? 'healthy' : 'unhealthy';
  const healthBadgeClass = { healthy: s.badgeHealthy, unhealthy: s.badgeUnhealthy, unknown: s.badgeUnknown }[health];
  const healthDotClass = { healthy: s.statusDotHealthy, unhealthy: s.statusDotUnhealthy, unknown: s.statusDotUnknown }[health];
  const healthLabel = { healthy: 'System healthy', unhealthy: 'System degraded or unreachable', unknown: 'System status not checked yet' }[health];
  const statusDotClass = `${s.statusDotBase} ${healthDotClass}`;

  return (
    <>
    <a href="#main-content" className={s.skipLink}>Skip to main content</a>
    <header data-layout="header" className={s.header}>
      <div className={s.headerLeft}>
        <h1 className={s.headerTitle}>Workspace</h1>
        <div className={s.headerBadges}>
          {/* Human-relevant status only — retrieval internals live in Settings. */}
          <span className={`${s.badge} ${healthBadgeClass}`} title={healthLabel}>
            <span className={statusDotClass} role="img" aria-label={healthLabel}></span>
            {systemStats.totalDocuments > 1000 ? (systemStats.totalDocuments / 1000).toFixed(1) + 'k' : systemStats.totalDocuments} documents indexed
          </span>
        </div>
      </div>
      <div className={s.headerRight}>
        {/* Settings is gated behind sign-in as a whole — don't offer a button
            that would open nothing. */}
        {isAuthenticated && (
          <button className={s.headerBtn} onClick={() => setShowSettings(true)}>
            <Icon name="Settings" size={18} /> Settings
          </button>
        )}
        {isAuthenticated && user ? (
          <div className={s.userMenu}>
            <div className={s.userAvatar}>{user.email?.[0]?.toUpperCase() || 'U'}</div>
            <span className={`${s.userName} hide-on-mobile`}>{user.email?.split('@')[0] || 'User'}</span>
            <button className={s.logoutBtn} onClick={handleLogout} title="Logout" aria-label="Log out">
              <Icon name="LogOut" size={16} />
            </button>
          </div>
        ) : (
          <div className={s.authButtons}>
            <button className={s.headerBtn} onClick={handleLogin}>
              <Icon name="LogIn" size={18} /> Sign In
            </button>
            <button className={`${s.headerBtn} ${s.headerBtnPrimary}`} onClick={handleShowSignup}>
              <Icon name="UserPlus" size={18} /> Register
            </button>
          </div>
        )}
      </div>
    </header>
    {/* Drawer toggles — position: fixed, visible only under the tablet
        breakpoint (styles/responsive.css) where the sidebars slide over. */}
    <button
      type="button"
      className="mobile-sidebar-toggle left-toggle"
      onClick={() => setLeftSidebarOpen(!leftSidebarOpen)}
      aria-label={leftSidebarOpen ? 'Close navigation' : 'Open navigation'}
      aria-expanded={leftSidebarOpen}
      aria-controls="left-sidebar"
    >
      <Icon name={leftSidebarOpen ? 'X' : 'Menu'} size={20} />
    </button>
    <button
      type="button"
      className="mobile-sidebar-toggle right-toggle"
      onClick={() => setRightPanelOpen(!rightPanelOpen)}
      aria-label={rightPanelOpen ? 'Close sources panel' : 'Open sources panel'}
      aria-expanded={rightPanelOpen}
      aria-controls="right-panel"
    >
      <Icon name={rightPanelOpen ? 'X' : 'PanelRight'} size={20} />
    </button>
    </>
  );
}
