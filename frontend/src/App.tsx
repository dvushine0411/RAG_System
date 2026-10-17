/**
 * System Role: Root component — gates the app behind authentication, then composes the sidebar
 *              (user bar + document library) and the chat panel.
 * Inputs: Auth state from useAuth; document & chat state from useDocuments / useChat.
 * Outputs: Splash while restoring the session, AuthPage for anonymous visitors, or the RAG workspace.
 */

import { AuthPage } from "./components/AuthPage";
import { ChatPanel } from "./components/ChatPanel";
import { DocumentPanel } from "./components/DocumentPanel";
import { UserBar } from "./components/UserBar";
import { useAuth } from "./hooks/useAuth";
import { useChat } from "./hooks/useChat";
import { useDocuments } from "./hooks/useDocuments";

function Workspace({ isAdmin }: { isAdmin: boolean }) {
  const docs = useDocuments();
  const chat = useChat();

  const scopeLabel =
    docs.selectedIds.length === 0
      ? `Phạm vi: tất cả tài liệu (${docs.documents.length})`
      : `Phạm vi: ${docs.selectedIds.length} tài liệu đã chọn`;

  return (
    <div className="app">
      <aside className="sidebar">
        <UserBar />
        <DocumentPanel
          documents={docs.documents}
          selectedIds={docs.selectedIds}
          uploading={docs.uploading}
          error={docs.error}
          notice={docs.notice}
          onUpload={docs.upload}
          onDelete={docs.remove}
          onToggle={docs.toggleSelected}
          onRefresh={docs.refresh}
          canManage={isAdmin}
        />
      </aside>
      <ChatPanel
        messages={chat.messages}
        streaming={chat.streaming}
        scopeLabel={scopeLabel}
        onSend={(text) => chat.send(text, docs.selectedIds)}
        onStop={chat.stop}
        onReset={chat.reset}
      />
    </div>
  );
}

export function App() {
  const { status, user } = useAuth();

  if (status === "loading") return <div className="splash muted">Đang khôi phục phiên đăng nhập…</div>;
  if (status === "anonymous" || !user) return <AuthPage />;
  // key: remount the workspace (fresh chat & documents state) when a different account signs in
  return <Workspace key={user.id} isAdmin={user.role === "admin"} />;
}
