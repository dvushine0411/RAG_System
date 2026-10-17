/**
 * System Role: Compact signed-in user badge (name, email, role) with a logout button.
 * Inputs: Current user and logout action from useAuth.
 * Outputs: Rendered user bar at the top of the sidebar.
 */

import { useAuth } from "../hooks/useAuth";

export function UserBar() {
  const { user, logout } = useAuth();
  if (!user) return null;

  return (
    <div className="user-bar">
      <div className="user-info">
        <strong title={user.email}>{user.name}</strong>
        <span className="muted">{user.email}</span>
      </div>
      <span className={`badge role-${user.role}`}>{user.role === "admin" ? "Admin" : "User"}</span>
      <button className="ghost" onClick={() => void logout()} title="Đăng xuất">
        Đăng xuất
      </button>
    </div>
  );
}
