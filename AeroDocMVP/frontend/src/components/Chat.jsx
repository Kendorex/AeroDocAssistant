import { useEffect, useMemo, useRef, useState } from "react";
import Message from "./Message";
import { classify, chat } from "../api/client";

const LS_KEY = "aerodoc_chats_v1";
const MAX_LEN = 1000;

function newChatSeed() {
    return {
        id: crypto.randomUUID?.() ?? String(Date.now()),
        title: "Новый чат",
        createdAt: Date.now(),
        updatedAt: Date.now(),
        messages: [
            {
                id: "m0",
                role: "assistant",
                text: "Привет! Я AeroDoc. Задай вопрос по авиационной документации 🙂",
            },
        ],
    };
}

function deriveTitleFromText(text) {
    const s = String(text || "")
        .trim()
        .replace(/\s+/g, " ");
    if (!s) return "Новый чат";
    return s.length > 28 ? `${s.slice(0, 28)}…` : s;
}

export default function Chat() {
    // ===== Chats state (sidebar + local persistence) =====
    const [chats, setChats] = useState(() => {
        try {
            const raw = localStorage.getItem(LS_KEY);
            if (!raw) return [newChatSeed()];
            const parsed = JSON.parse(raw);
            if (!Array.isArray(parsed) || parsed.length === 0) return [newChatSeed()];
            return parsed;
        } catch {
            return [newChatSeed()];
        }
    });

    const [activeChatId, setActiveChatId] = useState(() => chats?.[0]?.id);

    useEffect(() => {
        if (!chats.find((c) => c.id === activeChatId)) {
            setActiveChatId(chats[0]?.id);
        }
    }, [chats, activeChatId]);

    useEffect(() => {
        try {
            localStorage.setItem(LS_KEY, JSON.stringify(chats));
        } catch {

        }
    }, [chats]);

    const activeChat = useMemo(
        () => chats.find((c) => c.id === activeChatId) ?? chats[0],
        [chats, activeChatId]
    );

    const messages = activeChat?.messages ?? [];

    function updateActiveChat(updater) {
        setChats((prev) =>
            prev.map((c) => {
                if (c.id !== activeChatId) return c;
                const next = updater(c);
                return { ...next, updatedAt: Date.now() };
            })
        );
    }

    function createNewChat() {
        const c = newChatSeed();
        setChats((prev) => [c, ...prev]);
        setActiveChatId(c.id);
        setInput("");
    }

    function deleteChat(chatId) {
        setChats((prev) => {
            const next = prev.filter((c) => c.id !== chatId);
            return next.length ? next : [newChatSeed()];
        });
    }

    const [input, setInput] = useState("");
    const [loading, setLoading] = useState(false);
    const [loadingIdx, setLoadingIdx] = useState(0);

    const loadingPhrases = [
        "Думаю",
        "Ищу информацию",
        "Поиск по документам",
        "Сверяюсь с бумагами",
        "Формирую ответ",
        "Уточняю детали",
    ];

    const hints = [
        "Как подготовиться к буксировке ВС?",
        "Какие ограничения по ветру при рулении и буксировке?",
        "Какой порядок запуска ВС: ключевые шаги и проверки?",
        "Где найти нормы по давлению/азоту в стойках шасси?",
        "Как выполняется проверка системы противообледенения?",
        "Какие действия при срабатывании FIRE WARNING?",
        "Какой порядок отключения/подключения внешнего питания (GPU)?",
        "Какие интервалы и объёмы работ по ТО (A/B/C-check) для узла?",
        "Какие допустимые утечки/подтёки указаны для гидросистемы?",
        "Какие требования к установке заглушек, чехлов и блокировок перед обслуживанием?",
    ];

    const listRef = useRef(null);

    useEffect(() => {
        const el = listRef.current;
        if (!el) return;
        el.scrollTop = el.scrollHeight;
    }, [messages, loading, activeChatId]);

    useEffect(() => {
        if (!loading) return;

        setLoadingIdx(0);
        const id = setInterval(() => {
            setLoadingIdx(() => Math.floor(Math.random() * loadingPhrases.length));
        }, 15000);

        return () => clearInterval(id);
    }, [loading]);

    // ===== Hint rotation (smooth crossfade) =====
    const [hintIdx, setHintIdx] = useState(0);
    const [hintNextIdx, setHintNextIdx] = useState(1);
    const [hintMix, setHintMix] = useState(0);
    const [hintNoTransition, setHintNoTransition] = useState(false);

    useEffect(() => {
        const DURATION = 900;
        const HOLD = 5200;

        let timeoutId = null;
        let rafId = 0;
        let start = 0;

        const run = () => {
            setHintNextIdx((_) => (hintIdx + 1) % hints.length);

            start = performance.now();
            const tick = (t) => {
                const p = Math.min(1, (t - start) / DURATION);
                const eased = 1 - Math.pow(1 - p, 3);
                setHintMix(eased);

                if (p < 1) rafId = requestAnimationFrame(tick);
                else {
                    setHintNoTransition(true);
                    setHintIdx((i) => (i + 1) % hints.length);
                    setHintMix(0);
                    requestAnimationFrame(() => setHintNoTransition(false));
                }

            };

            rafId = requestAnimationFrame(tick);
            timeoutId = setTimeout(run, HOLD + DURATION);
        };

        timeoutId = setTimeout(run, HOLD);

        return () => {
            if (timeoutId) clearTimeout(timeoutId);
            if (rafId) cancelAnimationFrame(rafId);
        };
    }, [hintIdx, hints.length]);

    const canSend = useMemo(
        () => input.trim().length > 0 && !loading,
        [input, loading]
    );

    async function onSend() {
        const text = input.trim().slice(0, MAX_LEN);
        if (!text || loading || !activeChatId) return;

        setInput("");

        const userMsg = {
            id: crypto.randomUUID?.() ?? String(Date.now()),
            role: "user",
            text,
        };

        updateActiveChat((c) => {
            const isFirstUser = !c.messages.some((m) => m.role === "user");
            return {
                ...c,
                title: isFirstUser ? deriveTitleFromText(text) : c.title,
                messages: [...c.messages, userMsg],
            };
        });

        setLoading(true);

        try {
            const { label } = await classify(text);

            if (label === "greeting") {
                addAssistantMessageAnimated(
                    "Привет! Готов отвечать на твои вопросы."
                );
            } else if (label === "junk") {
                addAssistantMessageAnimated(
                    "Похоже на мусор или не по теме. Напиши вопрос чуть понятнее 🙂"
                );
            } else {
                const res = await chat(text);
                addAssistantMessageAnimated(res.answer);
            }
        } catch (e) {
            updateActiveChat((c) => ({
                ...c,
                messages: [
                    ...c.messages,
                    {
                        id: crypto.randomUUID?.() ?? String(Date.now()),
                        role: "assistant",
                        text: `Ошибка: ${String(e?.message || e)}`,
                    },
                ],
            }));
        } finally {
            setLoading(false);
        }
    }

    function onKeyDown(e) {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            onSend();
        }
    }

    function addAssistantMessageAnimated(fullText) {
        const id = crypto.randomUUID?.() ?? String(Date.now());

        updateActiveChat((c) => ({
            ...c,
            messages: [...c.messages, { id, role: "assistant", text: "" }],
        }));

        let i = 0;
        const step = 2;
        const delay = 14;

        const timer = setInterval(() => {
            i = Math.min(fullText.length, i + step);
            const slice = fullText.slice(0, i);

            updateActiveChat((c) => ({
                ...c,
                messages: c.messages.map((msg) =>
                    msg.id === id ? { ...msg, text: slice } : msg
                ),
            }));

            if (i >= fullText.length) clearInterval(timer);
        }, delay);
    }

    // ===== Sidebar UI =====
    const [collapsed, setCollapsed] = useState(false);

    useEffect(() => {
        const mq = window.matchMedia("(max-width: 980px)");

        const apply = () => setCollapsed(mq.matches);
        apply();

        if (mq.addEventListener) mq.addEventListener("change", apply);
        else mq.addListener(apply);

        return () => {
            if (mq.removeEventListener) mq.removeEventListener("change", apply);
            else mq.removeListener(apply);
        };
    }, []);

    return (
        <div
            style={{
                height: "100vh",
                display: "grid",
                gridTemplateColumns: collapsed ? "72px 1fr" : "300px 1fr",
                minHeight: 0,
            }}
        >
            {/* ===== Sidebar ===== */}
            <aside
                style={{
                    borderRight: "1px solid rgba(25,45,90,0.10)",
                    background: "rgba(255,255,255,0.72)",
                    backdropFilter: "blur(10px)",
                    minHeight: 0,
                    display: "grid",
                    gridTemplateRows: "auto auto 1fr",
                }}
            >
                {/* Top controls */}
                <div
                    style={{
                        padding: 12,
                        display: "flex",
                        gap: 10,
                        alignItems: "center",
                        justifyContent: "space-between",
                    }}
                >
                    <button
                        onClick={() => setCollapsed((v) => !v)}
                        title={collapsed ? "Развернуть" : "Свернуть"}
                        style={{
                            width: 36,
                            height: 36,
                            borderRadius: 12,
                            border: "1px solid rgba(25,45,90,0.12)",
                            background: "rgba(255,255,255,0.85)",
                            cursor: "pointer",
                        }}
                    >
                        ☰
                    </button>

                    {!collapsed && (
                        <button
                            onClick={createNewChat}
                            style={{
                                flex: 1,
                                height: 36,
                                borderRadius: 12,
                                border: "none",
                                background: "linear-gradient(180deg, #377dff, #2f6fe0)",
                                color: "#fff",
                                fontWeight: 700,
                                cursor: "pointer",
                                boxShadow: "0 10px 22px rgba(55,125,255,0.22)",
                            }}
                        >
                            Добавить чат
                        </button>
                    )}
                </div>

                {!collapsed && (
                    <div
                        style={{
                            padding: "0 12px 10px",
                            color: "var(--muted)",
                            fontSize: 12,
                        }}
                    >
                        Локально сохранено (localStorage)
                    </div>
                )}

                {/* Chat list */}
                <div
                    style={{
                        overflowY: "auto",
                        padding: collapsed ? 10 : 12,
                        minHeight: 0,
                    }}
                >
                    {chats
                        .slice()
                        .sort((a, b) => (b.updatedAt ?? 0) - (a.updatedAt ?? 0))
                        .map((c) => {
                            const active = c.id === activeChatId;

                            return (
                                <div
                                    key={c.id}
                                    style={{
                                        display: "flex",
                                        gap: collapsed ? 0 : 10,
                                        alignItems: "center",
                                        marginBottom: 10,
                                    }}
                                >
                                    <button
                                        onClick={() => setActiveChatId(c.id)}
                                        title={c.title}
                                        style={{
                                            flex: 1,
                                            textAlign: "left",
                                            height: 44,
                                            borderRadius: 14,
                                            border: active
                                                ? "1px solid rgba(55,125,255,0.45)"
                                                : "1px solid rgba(25,45,90,0.10)",
                                            background: active
                                                ? "linear-gradient(180deg, rgba(55,125,255,0.18), rgba(55,125,255,0.06))"
                                                : "rgba(255,255,255,0.85)",
                                            boxShadow: active
                                                ? "0 10px 22px rgba(55,125,255,0.12)"
                                                : "none",
                                            padding: collapsed ? "0 10px" : "0 12px",
                                            cursor: "pointer",
                                            color: "var(--text)",
                                            display: "flex",
                                            alignItems: "center",
                                            gap: 10,
                                            overflow: "hidden",
                                        }}
                                    >
                                        <span
                                            style={{
                                                width: 28,
                                                height: 28,
                                                borderRadius: 10,
                                                flexShrink: 0,
                                                display: "grid",
                                                placeItems: "center",
                                                background: active
                                                    ? "linear-gradient(180deg, #377dff, #2f6fe0)"
                                                    : "rgba(55,125,255,0.12)",
                                                border: active
                                                    ? "1px solid rgba(55,125,255,0.35)"
                                                    : "1px solid rgba(55,125,255,0.18)",
                                                color: active ? "#fff" : "rgba(55,125,255,0.95)",
                                                boxShadow: active
                                                    ? "0 10px 18px rgba(55,125,255,0.22)"
                                                    : "none",
                                            }}
                                        >
                                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                                                <path
                                                    d="M7 18l-3 3V6a3 3 0 0 1 3-3h10a3 3 0 0 1 3 3v7a3 3 0 0 1-3 3H10l-3 2z"
                                                    stroke="currentColor"
                                                    strokeWidth="2"
                                                    strokeLinejoin="round"
                                                />
                                            </svg>
                                        </span>

                                        {!collapsed && (
                                            <span
                                                style={{
                                                    flex: 1,
                                                    fontWeight: 500,
                                                    whiteSpace: "nowrap",
                                                    overflow: "hidden",
                                                    textOverflow: "ellipsis",
                                                }}
                                            >
                                                {c.title}
                                            </span>
                                        )}
                                    </button>

                                    {!collapsed && (
                                        <button
                                            onClick={() => deleteChat(c.id)}
                                            title="Удалить чат"
                                            style={{
                                                width: 42,
                                                height: 42,
                                                borderRadius: 14,
                                                border: "1px solid rgba(25,45,90,0.10)",
                                                background: "rgba(255,255,255,0.85)",
                                                cursor: "pointer",
                                            }}
                                        >
                                            🗑️
                                        </button>
                                    )}
                                </div>
                            );
                        })}
                </div>
            </aside>

            {/* ===== Main (твоя текущая структура внутри) ===== */}
            <div
                style={{
                    height: "100vh",
                    display: "grid",
                    gridTemplateRows: "auto 1fr auto",
                    minHeight: 0,
                }}
            >
                {/* Header */}
                <div
                    style={{
                        padding: "14px 18px",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        borderBottom: "1px solid rgba(25,45,90,0.10)",
                        backdropFilter: "blur(10px)",
                        background: "rgba(255,255,255,0.72)",
                    }}
                >
                    <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                        <img
                            src="/avatars/app.png"
                            alt="AeroDoc App"
                            style={{
                                width: 42,
                                height: 42,
                                borderRadius: 12,
                                objectFit: "cover",
                                boxShadow: "0 10px 24px rgba(55,125,255,0.22)",
                                background: "#fff",
                            }}
                        />

                        <div>
                            <div style={{ fontWeight: 800, letterSpacing: 0.2 }}>
                                AeroDoc Assistant
                            </div>

                            <div style={{ fontSize: 12, color: "var(--muted)" }}>
                                <span className="headerHint">
                                    Отвечаю по документации с точными ссылками •{" "}
                                </span>
                                {activeChat?.title ?? "Новый чат"}
                            </div>
                        </div>
                    </div>

                    <div
                        style={{
                            display: "flex",
                            alignItems: "center",
                            gap: 8,
                            padding: "6px 12px",
                            borderRadius: 999,
                            border: loading
                                ? "1px solid rgba(250,204,21,0.55)"
                                : "1px solid rgba(34,197,94,0.45)",
                            background: loading
                                ? "rgba(250,204,21,0.12)"
                                : "rgba(34,197,94,0.10)",
                            fontSize: 12,
                            color: "rgba(11,27,58,0.78)",
                        }}
                    >
                        <span>Статус</span>
                        <span
                            className="statusDot"
                            style={{
                                "--dot": loading ? "#facc15" : "#22c55e",
                                "--dotSoft": loading
                                    ? "rgba(250,204,21,0.55)"
                                    : "rgba(34,197,94,0.55)",
                            }}
                        />
                    </div>
                </div>

                {/* Main */}
                <div
                    style={{
                        display: "flex",
                        justifyContent: "center",
                        padding: 18,
                        minHeight: 0,
                        background: "rgba(15, 25, 55, 0.04)",
                    }}
                >
                    <div
                        style={{
                            borderRadius: 22,
                            width: "100%",
                            maxWidth: 980,
                            border: "1px solid rgba(25,45,90,0.10)",
                            background: "rgba(255,255,255,0.65)",
                            boxShadow: "var(--shadow-soft)",
                            overflow: "hidden",
                            position: "relative",
                            minHeight: 0,
                        }}
                    >
                        <div
                            ref={listRef}
                            className="chatScroll"
                            style={{
                                height: "100%",
                                overflowY: "auto",
                                padding: 18,
                                minHeight: 0,
                                scrollBehavior: "smooth",
                            }}
                        >
                            {messages.map((msg) => (
                                <Message key={msg.id} role={msg.role} text={msg.text} />
                            ))}

                            {loading && (
                                <Message
                                    role="assistant"
                                    text={
                                        <span>
                                            {loadingPhrases[loadingIdx]}
                                            <span className="typingDots">
                                                <span></span>
                                                <span></span>
                                                <span></span>
                                            </span>
                                        </span>
                                    }
                                />
                            )}
                        </div>

                        <div className="fadeTop" />
                        <div className="fadeBottom" />
                    </div>
                </div>

                {/* Composer */}
                <div
                    style={{
                        padding: "14px 18px",
                        display: "flex",
                        justifyContent: "center",
                        borderTop: "1px solid rgba(25,45,90,0.10)",
                        background: "rgba(255,255,255,0.72)",
                        backdropFilter: "blur(10px)",
                    }}
                >
                    <div
                        style={{
                            width: "100%",
                            maxWidth: 980,
                        }}
                    >
                        <div
                            style={{
                                position: "relative",
                                borderRadius: 18,
                                border: "1px solid rgba(25,45,90,0.14)",
                                background: "rgba(255,255,255,0.9)",
                                boxShadow: "var(--shadow-soft)",
                                padding: "10px 52px 10px 10px",
                            }}
                        >
                            <textarea
                                value={input}
                                maxLength={MAX_LEN}
                                onChange={(e) => setInput(e.target.value.slice(0, MAX_LEN))}
                                onKeyDown={onKeyDown}
                                rows={2}
                                placeholder="Напиши вопрос… (Enter — отправить, Shift+Enter — новая строка)"
                                style={{
                                    width: "100%",
                                    border: "none",
                                    outline: "none",
                                    resize: "none",
                                    background: "transparent",
                                    color: "var(--text)",
                                    fontSize: 15,
                                    lineHeight: 1.4,
                                    paddingBottom: 26,
                                }}
                            />

                            <div
                                style={{
                                    display: "flex",
                                    alignItems: "center",
                                    gap: 12,
                                    marginTop: 6,
                                }}
                            >
                                <div
                                    style={{
                                        fontSize: 12,
                                        color: "var(--muted)",
                                        position: "relative",
                                        minHeight: 18,
                                        paddingRight: 8,
                                        overflow: "hidden",
                                    }}
                                >
                                    Подсказка:{" "}
                                    <span
                                        style={{
                                            position: "relative",
                                            display: "inline-block",
                                            verticalAlign: "top",
                                        }}
                                    >
                                        {/* current */}
                                        <span
                                            style={{
                                                position: "absolute",
                                                left: 0,
                                                top: 0,
                                                whiteSpace: "nowrap",
                                                opacity: 1 - hintMix,
                                                filter: `blur(${Math.max(0, Math.min(1, hintMix)) * 0.9}px)`,
                                                transition: hintNoTransition
                                                    ? "none"
                                                    : "opacity 520ms cubic-bezier(0.22, 1, 0.36, 1), filter 520ms cubic-bezier(0.22, 1, 0.36, 1)",
                                                willChange: "opacity, filter",
                                                pointerEvents: "none",
                                            }}
                                        >
                                            {hints[hintIdx]}
                                        </span>

                                        {/* next */}
                                        <span
                                            style={{
                                                position: "absolute",
                                                left: 0,
                                                top: 0,
                                                whiteSpace: "nowrap",
                                                opacity: hintMix,
                                                filter: `blur(${Math.max(0, Math.min(1, 1 - hintMix)) * 0.9}px)`,
                                                transition: hintNoTransition
                                                    ? "none"
                                                    : "opacity 520ms cubic-bezier(0.22, 1, 0.36, 1), filter 520ms cubic-bezier(0.22, 1, 0.36, 1)",
                                                willChange: "opacity, filter",
                                                pointerEvents: "none",
                                            }}
                                        >
                                            {hints[hintNextIdx]}
                                        </span>

                                        {/* spacer to preserve layout width */}
                                        <span style={{ visibility: "hidden", whiteSpace: "nowrap" }}>
                                            {hints[hintMix < 0.5 ? hintIdx : hintNextIdx]}
                                        </span>
                                    </span>
                                </div>

                                <div
                                    style={{
                                        fontSize: 12,
                                        color: "var(--muted)",
                                        marginLeft: "auto",
                                        paddingRight: 10,
                                    }}
                                >
                                    {input.length}/{MAX_LEN}
                                </div>

                                <button
                                    onClick={onSend}
                                    disabled={!canSend}
                                    aria-label="Отправить"
                                    style={{
                                        position: "absolute",
                                        right: 12,
                                        bottom: 10,
                                        width: 38,
                                        height: 38,
                                        borderRadius: "50%",
                                        border: "none",
                                        background: canSend
                                            ? "linear-gradient(180deg, #377dff, #2f6fe0)"
                                            : "rgba(55,125,255,0.25)",
                                        color: "#fff",
                                        cursor: canSend ? "pointer" : "not-allowed",
                                        display: "flex",
                                        alignItems: "center",
                                        justifyContent: "center",
                                        boxShadow: canSend
                                            ? "0 10px 22px rgba(55,125,255,0.35)"
                                            : "none",
                                    }}
                                >
                                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                                        <path
                                            d="M4 12h14M12 6l6 6-6 6"
                                            stroke="currentColor"
                                            strokeWidth="2"
                                            strokeLinecap="round"
                                            strokeLinejoin="round"
                                        />
                                    </svg>
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
