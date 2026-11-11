/**
 * DEV-ONLY in-memory messaging backend for `npm run dev:mock` (see mock.js): student <-> faculty chats
 * (/api/chat/*), and faculty <-> admin messages (/api/admin-messages/*).
 * Mirrors the real contract (docs/api/chat.md): ticks, replies, unsend, delete-for-me, 15-minute edit window,
 * `after_id` + `updated_since` polling, typing and presence. The "other side" reads your messages after a moment
 * and answers a few seconds later so the whole flow can be tried by hand.
 */
const MIN = 60_000;
const now = () => Date.now();
const fmt = (ms) => new Date(ms).toISOString().slice(0, 19).replace("T", " ");

const PEOPLE = {
  1: { name: "Ananya Rao", role: "STUDENT", id: 3, usn: "1AB21CS014", seen: now() - 30 * MIN },
  2: { name: "Dr. Meera Iyer", role: "FACULTY", id: 5, code: "FAC001", dept: "AIML", online: true },
  3: { name: "Campus Admin", role: "ADMIN", online: true },
  4: { name: "Prof. Rahul Verma", role: "FACULTY", id: 6, code: "FAC002", dept: "AIML", seen: now() - 2 * 3600_000 },
  6: { name: "Karthik N", role: "STUDENT", id: 7, usn: "1AB21CS031", seen: now() - 26 * 3600_000 },
};
// conversations: id -> { kind: "chat" | "admin", a, b } (admin: id is the faculty user id, b is the admin)
const CONVS = {
  "chat:1": { kind: "chat", id: 1, a: 1, b: 2 },
  "chat:2": { kind: "chat", id: 2, a: 1, b: 4 },
  "chat:3": { kind: "chat", id: 3, a: 6, b: 2 },
  "admin:2": { kind: "admin", id: 2, a: 2, b: 3 },
  "admin:4": { kind: "admin", id: 4, a: 4, b: 3 },
};

let nextId = 1;
const messages = [];
function add(conv, sender, text, ago, extra = {}) {
  const created = now() - ago;
  messages.push({ id: nextId++, conv, sender, text, created, updated: created, delivered: created + 1000, seen: created + 5000, ...extra });
}
add("chat:1", 2, "Good morning Ananya. Please share your project abstract by Friday.", 26 * 3600_000);
add("chat:1", 1, "Good morning ma'am, I will send it today.", 25.9 * 3600_000);
add("chat:1", 2, "Also, the meeting on Thursday is confirmed for 11:30.", 40 * MIN, { seen: null });
add("chat:1", 2, "Bring the draft report with you.", 39 * MIN, { seen: null });
add("chat:2", 4, "Your lab record is pending signature.", 3 * 24 * 3600_000);
// stress content for chat QA: long text, unbroken string, file + image attachments, quote, tombstone, enough history to scroll
for (let i = 0; i < 14; i++) add("chat:2", i % 2 ? 1 : 4, i % 2 ? "Okay sir, noted for item " + (i + 1) + "." : "Please also check item " + (i + 1) + " before the review.", (3 * 24 * 3600_000) - (i + 1) * 20 * MIN);
add("chat:2", 1, "Sir, I have attached the record. Could you please check it and let me know if anything is missing? I will also bring the printed copy tomorrow morning along with the signed attendance sheet from the lab in-charge.", 2 * 3600_000);
add("chat:2", 1, "", 110 * MIN, { attachment: { name: "lab-record-final-version-with-a-very-long-file-name-v3.pdf", type: "pdf", url: "/uploads/chat/x.pdf" } });
add("chat:2", 1, "Circuit diagram", 100 * MIN, { attachment: { name: "diagram.png", type: "png", url: "/favicon.svg" } });
add("chat:2", 4, "https://example.com/some/really/long/path/that/never/breaks/because/it/has/no/spaces/at/all/1234567890/abcdefghijklmnopqrstuvwxyz", 90 * MIN);
add("chat:2", 4, null, 80 * MIN, { unsent: now() - 80 * MIN });
add("chat:2", 4, "Will check it tomorrow.", 70 * MIN, { reply_to: messages.length - 3 });
add("chat:2", 4, "Also remember the viva.", 20 * MIN, { seen: null });
add("chat:2", 4, "Bring the printed copy.", 10 * MIN, { seen: null });
add("chat:3", 6, "Ma'am, can I get a revaluation form?", 5 * 3600_000);
add("admin:2", 3, "Please confirm the exam duty roster.", 2 * 3600_000);

const typing = new Map(); // `${conv}:${user}` -> expiry
const replies = []; // scheduled auto-replies { at, conv, sender, text }

const mine = (m, uid) => m.sender === uid;
const statusOf = (m) => (m.seen ? "seen" : m.delivered ? "delivered" : "sent");
const imageType = (t) => ["png", "jpg", "jpeg"].includes((t || "").toLowerCase());

function tick() {
  for (let i = replies.length - 1; i >= 0; i--) {
    const r = replies[i];
    if (r.at <= now()) { replies.splice(i, 1); add(r.conv, r.sender, r.text, 0, { delivered: null, seen: null }); }
  }
  // messages I send here are delivered after 1 s and seen after 3 s by the (simulated) other side
  for (const m of messages) {
    if (!m.fresh) continue;
    if (!m.delivered && now() - m.created > 1000) { m.delivered = m.created + 1000; m.updated = now(); }
    if (!m.seen && now() - m.created > 3000) { m.seen = now(); m.updated = now(); }
  }
}

function party(uid, viewer) {
  const p = PEOPLE[uid];
  const online = !!p.online;
  const base = { full_name: p.name, profile_picture_url: null, online, last_active_at: p.seen ? fmt(p.seen) : null };
  if (p.role === "FACULTY") return { ...base, role: "FACULTY", id: viewer?.role === "ADMIN" ? uid : p.id, user_id: uid, code: p.code, faculty_code: p.code, department: p.dept };
  if (p.role === "STUDENT") return { ...base, role: "STUDENT", id: p.id, code: p.usn, usn: p.usn, class: { section_id: 3, branch: "CSE", department: "AIML", year: "3rd Year", section: "A", label: "CSE → AIML → 3rd Year → A" } };
  return { ...base, role: "ADMIN", id: uid, user_id: uid, code: null };
}

function item(m, viewer, all) {
  const unsent = !!m.unsent;
  const target = m.reply_to && !unsent ? all.find((x) => x.id === m.reply_to) : null;
  const age = now() - m.created;
  return {
    id: m.id, is_mine: mine(m, viewer.id), sender_name: PEOPLE[m.sender].name,
    message_text: unsent ? null : m.text,
    attachment: !unsent && m.attachment ? { url: null, ...m.attachment, is_image: imageType(m.attachment.type) } : null,
    status: statusOf(m), is_seen: !!m.seen, delivered_at: m.delivered ? fmt(m.delivered) : null, seen_at: m.seen ? fmt(m.seen) : null,
    is_edited: !!m.edited && !unsent, is_unsent: unsent, unsent_at: m.unsent ? fmt(m.unsent) : null,
    can_edit: mine(m, viewer.id) && !unsent && !m.attachment && age <= 15 * MIN, can_unsend: mine(m, viewer.id) && !unsent,
    reply_to: target ? {
      id: target.id, is_mine: mine(target, viewer.id), sender_user_id: target.sender, sender_name: PEOPLE[target.sender].name,
      text_preview: target.unsent ? null : (target.text || "").slice(0, 120) || null, attachment_kind: target.attachment && !target.unsent ? "file" : null,
      attachment_name: target.attachment?.name || null, unsent: !!target.unsent,
    } : null,
    created_at: fmt(m.created), updated_at: fmt(m.updated),
  };
}

const visible = (m, uid) => !(m.hidden || []).includes(uid);
const otherOf = (c, uid) => (c.a === uid ? c.b : c.a);
const convsFor = (kind, viewer) => Object.values(CONVS).filter((c) => c.kind === kind && (viewer.role === "ADMIN" ? kind === "admin" : c.a === viewer.id || c.b === viewer.id));

function summary(c, viewer) {
  const msgs = messages.filter((m) => m.conv === `${c.kind}:${c.id}` && visible(m, viewer.id));
  const last = msgs[msgs.length - 1];
  const o = viewer.role === "ADMIN" ? c.a : otherOf(c, viewer.id);
  const unread = msgs.filter((m) => !mine(m, viewer.id) && !m.seen && !m.unsent).length;
  const preview = !last ? null : last.unsent ? (mine(last, viewer.id) ? "You unsent a message" : `${PEOPLE[last.sender].name} unsent a message`) : last.text || `Attachment: ${last.attachment?.name || "file"}`;
  const other = { ...party(o, viewer), typing: (typing.get(`${c.kind}:${c.id}:${o}`) || 0) > now() };
  const row = {
    other, unread_count: unread, last_message: preview, last_message_at: last ? fmt(last.created) : null,
    last_message_is_mine: last ? mine(last, viewer.id) : null, last_message_is_unsent: last ? !!last.unsent : null,
    last_message_status: last && mine(last, viewer.id) ? statusOf(last) : null, updated_at: last ? fmt(last.created) : fmt(now()),
  };
  return c.kind === "chat" ? { chat_id: c.id, ...row } : { conversation_id: c.id, ...row };
}

export function handleChatMock({ method, path, url, body, user, json, err }) {
  if (!user || !/^\/api\/(chat|admin-messages)/.test(path)) return null;
  tick();
  const q = (k) => url.searchParams.get(k);
  const sort = (rows) => rows.sort((x, y) => (y.last_message_at || "").localeCompare(x.last_message_at || ""));

  if (user.role === "ADMIN" && !path.startsWith("/api/admin-messages")) return null;

  const kind = path.startsWith("/api/chat") ? "chat" : "admin";
  const base = kind === "chat" ? "/api/chat" : "/api/admin-messages";
  const rest = path.slice(base.length);
  const convOf = (id) => { const c = CONVS[`${kind}:${id}`]; return c && convsFor(kind, user).includes(c) ? c : null; };
  const key = (c) => `${c.kind}:${c.id}`;

  if (method === "GET" && rest === "") {
    const rows = sort(convsFor(kind, user).map((c) => summary(c, user)));
    return json(200, { items: rows, total: rows.length, total_unread: rows.reduce((n, r) => n + r.unread_count, 0) });
  }
  if (kind === "chat" && method === "POST" && rest === "/open") {
    const c = Object.values(CONVS).find((x) => x.kind === "chat" && convsFor("chat", user).includes(x));
    return c ? json(200, { ok: true, message: "Chat opened.", chat_id: c.id }) : err(403, "forbidden", "You do not have permission to message this person.");
  }

  let m = rest.match(/^\/messages\/(\d+)\/(edit|unsend|delete-for-me)$/);
  if (m && method === "POST") {
    const msg = messages.find((x) => x.id === Number(m[1]) && CONVS[x.conv].kind === kind);
    if (!msg || !convOf(CONVS[msg.conv].id)) return err(404, "not_found", "Message not found.");
    if (m[2] === "delete-for-me") { msg.hidden = [...(msg.hidden || []), user.id]; return json(200, { ok: true, id: msg.id }); }
    if (msg.sender !== user.id) return err(403, "forbidden", `You do not have permission to ${m[2]} this message.`);
    if (m[2] === "unsend") { if (!msg.unsent) { msg.unsent = now(); msg.text = null; msg.attachment = null; msg.reply_to = null; msg.updated = now(); } return json(200, { ok: true, message: "Message unsent.", item: item(msg, user, messages) }); }
    if (msg.unsent) return err(409, "conflict", "This message was already unsent.");
    if (now() - msg.created > 15 * MIN) return err(409, "conflict", "The 15-minute edit window has already passed for this message.");
    msg.text = String(body.message_text || "").trim(); msg.edited = true; msg.updated = now();
    return json(200, { ok: true, message: "Message updated.", item: item(msg, user, messages) });
  }

  // admin conversation addressed by faculty user id (a POST to the collection names it in the body)
  const idMatch = rest.match(/^\/(\d+)(\/messages|\/typing)?$/);
  const cid = kind === "admin" && method === "POST" && rest === "" ? (user.role === "ADMIN" ? body.recipient_user_id : user.id) : idMatch ? Number(idMatch[1]) : null;
  const c = cid != null ? convOf(cid) : null;
  if (!c) return err(404, "not_found", "Conversation not found.");

  if (method === "POST" && (rest === "" || idMatch?.[2] === "/messages")) {
    const text = String(body.message_text || "").trim();
    if (!text) return err(400, "validation_error", "Please enter a message or attach a file.", { message_text: "Please enter a message or attach a file." });
    const target = body.reply_to_id ? messages.find((x) => x.id === body.reply_to_id && x.conv === key(c)) : null;
    if (body.reply_to_id && !target) return err(400, "validation_error", "You can only reply to a message in this conversation.");
    add(key(c), user.id, text, 0, { delivered: null, seen: null, reply_to: target?.id || null, fresh: true });
    const sent = messages[messages.length - 1];
    const o = otherOf(c, user.id);
    typing.set(`${key(c)}:${o}`, now() + 4500);
    replies.push({ at: now() + 4500, conv: key(c), sender: o, text: ["Got it, thank you!", "Okay, noted.", "Sure, let's do that."][sent.id % 3] });
    return json(201, { ok: true, message: "Message sent.", id: sent.id, item: item(sent, user, messages) });
  }
  if (method === "POST" && idMatch?.[2] === "/typing") { typing.set(`${key(c)}:${user.id}`, now() + 5000); return json(200, { ok: true }); }

  if (method === "GET") {
    const after = Number(q("after_id") || 0);
    const since = q("updated_since") ? q("updated_since").replace("T", " ").slice(0, 19) : null;
    const all = messages.filter((x) => x.conv === key(c) && visible(x, user.id));
    all.filter((x) => !mine(x, user.id) && !x.seen).forEach((x) => { x.seen = now(); x.delivered = x.delivered || now(); x.updated = now(); });
    const rows = all.filter((x) => x.id > after || (since && fmt(x.updated) >= since));
    const o = user.role === "ADMIN" ? c.a : otherOf(c, user.id);
    return json(200, {
      chat: { id: c.id, other: { ...party(o, user), typing: (typing.get(`${key(c)}:${o}`) || 0) > now() }, created_at: fmt(now()), updated_at: fmt(now()) },
      messages: rows.map((x) => item(x, user, messages)), last_id: Math.max(after, ...rows.map((x) => x.id)), server_time: fmt(now()),
    });
  }
  return null;
}
