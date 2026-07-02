import AdminClient from "./AdminClient";

// Everything on this page depends on the admin token entered at runtime —
// never prerender it with stale data.
export const dynamic = "force-dynamic";

export default function AdminPage() {
  return <AdminClient />;
}
