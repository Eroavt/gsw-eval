import { submissions } from "../arena/production.js";

export const POST = (request) => submissions().submit(request);
export const OPTIONS = (request) => submissions().submit(request);
