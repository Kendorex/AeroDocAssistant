export default function Message({ role, text }) {
  const isUser = role === "user";
  const AVATAR = 44;

  const avatarSrc = isUser
    ? "/avatars/user.png"
    : "/avatars/assistant.png";

  const bubbleStyle = {
    maxWidth: 760,
    minHeight: AVATAR,
    padding: "12px 14px",
    borderRadius: 16,
    border: "1px solid rgba(25,45,90,0.12)",
    background: isUser
      ? "linear-gradient(180deg, rgba(55,125,255,0.18), rgba(55,125,255,0.06))"
      : "rgba(255,255,255,0.92)",
    boxShadow: isUser
      ? "0 10px 22px rgba(55,125,255,0.14)"
      : "0 10px 22px rgba(9,30,66,0.08)",
    whiteSpace: "pre-wrap",
    lineHeight: 1.45,
    overflowWrap: "anywhere",
    wordBreak: "break-word",
    display: "flex",
    alignItems: "center",
  };

  return (
    <div
      style={{
        display: "flex",
        gap: 12,
        margin: "10px 0",
        justifyContent: isUser ? "flex-end" : "flex-start",
        alignItems: "flex-start",
      }}
    >
      {!isUser && (
        <img
          src={avatarSrc}
          alt="assistant avatar"
          style={{
            width: AVATAR,
            height: AVATAR,
            borderRadius: "50%",
            objectFit: "cover",
            flexShrink: 0,
          }}
        />
      )}

      <div style={bubbleStyle}>
        <div style={{ width: "100%" }}>{text}</div>
      </div>

      {isUser && (
        <img
          src={avatarSrc}
          alt="user avatar"
          style={{
            width: AVATAR,
            height: AVATAR,
            borderRadius: "50%",
            objectFit: "cover",
            flexShrink: 0,
          }}
        />
      )}
    </div>
  );
}
