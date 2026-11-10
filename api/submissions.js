import { submissions } from "../arena/production.js";

export const GET = (request) => submissions().list(request);
