/**
 * Test Oturumu — sayfa-seviyesi layout.
 *
 * Parent App Router layout'unu (uygulama shell'i) override eder: bu sayfa
 * saha tableti için tam-ekran kendi topbar'ıyla render olur (physical-tests
 * ile aynı "shell bypass" yöntemi).
 */
export default function TestSessionLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
