import { submissions } from "../arena/production.js";

export const GET = (request) => submissions().progress(request);
