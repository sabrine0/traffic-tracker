interface NavbarProps {
  onToggleSidebar: () => void;
  sidebarOpen: boolean;
}

export default function Navbar({ onToggleSidebar, sidebarOpen }: NavbarProps) {
  return (
    <nav aria-label="Main navigation" className="fixed top-0 left-0 right-0 z-50 flex h-12 items-center justify-between bg-gray-900 px-4 text-white shadow-md">
      <div className="flex items-center gap-3">
        <button
          onClick={onToggleSidebar}
          className="rounded p-2 hover:bg-gray-700 md:hidden min-h-[44px] min-w-[44px] flex items-center justify-center"
          aria-label="Toggle sidebar"
        >
          <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            {sidebarOpen ? (
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            ) : (
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            )}
          </svg>
        </button>
        <span className="text-lg font-bold tracking-wide">Map2CAD</span>
      </div>

      <a
        href="/admin"
        className="inline-flex min-h-[40px] items-center gap-2 rounded border border-gray-700 bg-gray-800 px-3 py-2 text-sm font-medium text-white transition hover:bg-gray-700"
      >
        <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
        </svg>
        <span>Dashboard</span>
      </a>
    </nav>
  );
}
