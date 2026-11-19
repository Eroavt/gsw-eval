import { submissions } from "../server/production.js";

export const GET = (request) => submissions().list(request);
