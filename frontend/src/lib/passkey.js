/**
 * WebAuthn (passkey) helpers: the server speaks JSON with base64url strings, the browser API wants ArrayBuffers.
 * Server options come from py_webauthn (`/api/auth/admin-passkey/options`, `/api/admin/passkeys/options`).
 */

export const passkeysSupported = () => typeof window !== "undefined" && !!window.PublicKeyCredential && !!navigator.credentials;

export async function conditionalPasskeysAvailable() {
  try {
    return passkeysSupported() && !!(await window.PublicKeyCredential.isConditionalMediationAvailable?.());
  } catch {
    return false;
  }
}

export function b64urlToBuffer(value) {
  const base64 = value.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(value.length / 4) * 4, "=");
  const bin = atob(base64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i += 1) bytes[i] = bin.charCodeAt(i);
  return bytes.buffer;
}

export function bufferToB64url(buffer) {
  const bytes = new Uint8Array(buffer);
  let bin = "";
  for (let i = 0; i < bytes.length; i += 1) bin += String.fromCharCode(bytes[i]);
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

const withDecodedIds = (list) => (list || []).map((c) => ({ ...c, id: b64urlToBuffer(c.id) }));

/** Create a passkey from server registration options -> JSON for POST /api/admin/passkeys/verify. */
export async function createPasskey(options) {
  const credential = await navigator.credentials.create({
    publicKey: {
      ...options,
      challenge: b64urlToBuffer(options.challenge),
      user: { ...options.user, id: b64urlToBuffer(options.user.id) },
      excludeCredentials: withDecodedIds(options.excludeCredentials),
    },
  });
  const r = credential.response;
  return {
    id: credential.id,
    rawId: bufferToB64url(credential.rawId),
    type: credential.type,
    response: {
      clientDataJSON: bufferToB64url(r.clientDataJSON),
      attestationObject: bufferToB64url(r.attestationObject),
      transports: r.getTransports?.() ?? [],
    },
    clientExtensionResults: credential.getClientExtensionResults?.() ?? {},
  };
}

/**
 * Ask the browser for a passkey assertion -> JSON for POST /api/auth/admin-passkey/verify.
 * `mediation: "conditional"` shows passkeys in the autofill list of an input that has autocomplete="... webauthn".
 */
export async function getPasskey(options, { mediation, signal } = {}) {
  const credential = await navigator.credentials.get({
    publicKey: {
      ...options,
      challenge: b64urlToBuffer(options.challenge),
      allowCredentials: withDecodedIds(options.allowCredentials),
    },
    ...(mediation ? { mediation } : {}),
    ...(signal ? { signal } : {}),
  });
  const r = credential.response;
  return {
    id: credential.id,
    rawId: bufferToB64url(credential.rawId),
    type: credential.type,
    response: {
      clientDataJSON: bufferToB64url(r.clientDataJSON),
      authenticatorData: bufferToB64url(r.authenticatorData),
      signature: bufferToB64url(r.signature),
      ...(r.userHandle ? { userHandle: bufferToB64url(r.userHandle) } : {}),
    },
    clientExtensionResults: credential.getClientExtensionResults?.() ?? {},
  };
}

/** Friendly text for a failed browser WebAuthn call (the user cancelling is not an error worth shouting about). */
export function passkeyErrorMessage(err) {
  switch (err?.name) {
    case "NotAllowedError": return "The passkey request was cancelled or timed out.";
    case "InvalidStateError": return "This passkey is already registered on this device.";
    case "SecurityError": return "Passkeys cannot be used from this website address.";
    case "NotSupportedError": return "This device or browser cannot create the required kind of passkey.";
    default: return err?.message || "The passkey could not be used.";
  }
}
