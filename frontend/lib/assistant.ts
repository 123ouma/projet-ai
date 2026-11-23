// Appels au backend pour l'assistant LLM (SA-36 / SA-37).
// Le navigateur parle uniquement au backend FastAPI, jamais directement au LLM (SA-4 §3).

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export type Language = "fr" | "en" | "arabizi" | "tn";
export type Intent =
  | "orientation"
  | "information"
  | "registration"
  | "confirm"
  | "reschedule"
  | "cancel"
  | "unclear";

export type Understanding = {
  intent: Intent;
  budget_dt: number | null;
  online: boolean | null;
  normalized_message: string;
  language: string;
  pipeline_version: string;
  model_id: string;
  mock: boolean;
};

export type Profil = {
  intent: Intent | null;
  budget_dt: number | null;
  online: boolean | null;
};

export type ChatResponse = {
  session_id: string;
  understanding: Understanding;
  profil: Profil;
  history_sent: number;
};

export type LLMHealth = {
  reachable: boolean;
  status: string | null;
  model: string | null;
  mock: boolean | null;
};

export const INTENT_LABELS: Record<Intent, string> = {
  orientation: "Orientation",
  information: "Demande d'information",
  registration: "Préinscription",
  confirm: "Confirmation",
  reschedule: "Report de rendez-vous",
  cancel: "Annulation",
  unclear: "Demande pas claire",
};

/** Erreur lisible pour l'étudiant, avec le code HTTP pour le débogage. */
export class AssistantError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

async function detail(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body?.detail === "string") return body.detail;
  } catch {
    // corps non JSON : on garde le message par défaut
  }
  return `Erreur ${response.status}`;
}

/** SA-37 : envoie un message dans une conversation (l'historique est géré par le backend). */
export async function sendChatMessage(
  sessionId: string,
  message: string,
  language: Language,
): Promise<ChatResponse> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}/assistant/chat/${sessionId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, language }),
    });
  } catch {
    throw new AssistantError("Le serveur SmartCampus est injoignable. Vérifiez que le backend est lancé.", 0);
  }
  if (!response.ok) throw new AssistantError(await detail(response), response.status);
  return response.json();
}

/** « Nouvelle conversation » : efface la mémoire de la session (SA-26). */
export async function resetConversation(sessionId: string): Promise<void> {
  try {
    await fetch(`${API_URL}/conversations/${sessionId}`, { method: "DELETE" });
  } catch {
    // sans effet si le backend est arrêté : la nouvelle session repart de zéro de toute façon
  }
}

export async function getLLMHealth(): Promise<LLMHealth | null> {
  try {
    const response = await fetch(`${API_URL}/assistant/health`);
    if (!response.ok) return null;
    return response.json();
  } catch {
    return null;
  }
}
