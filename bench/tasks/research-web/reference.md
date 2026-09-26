# MCP transports and authorization (reference, based on the 2025-11-25 specification)

## Transports
MCP messages are JSON-RPC 2.0, UTF-8 encoded. The specification defines two standard transports, and implementations may add custom ones.

- **stdio:** the client launches the server as a subprocess and exchanges newline-delimited JSON-RPC messages over stdin and stdout; the server may log to stderr. Use it for local tools running on the user's machine. It is simple, has no network exposure, and every client should support it.
- **Streamable HTTP:** the server is an independent process exposing one HTTP endpoint that accepts POST (client messages) and GET (a server-to-client stream). It may answer with plain JSON or open a Server-Sent Events stream for streamed responses and server requests. Sessions are tracked with the `Mcp-Session-Id` header, and clients send `MCP-Protocol-Version` on each request. Use it for remote or shared servers with many clients. Servers must validate the `Origin` header to prevent DNS rebinding, and local servers should bind to localhost only.
- **HTTP+SSE (legacy):** the original 2024-11-05 transport, with separate SSE and POST endpoints. It was replaced by Streamable HTTP in 2025-03-26 and is kept only for backwards compatibility.

## Authorization for remote servers
Authorization is optional and applies to HTTP-based transports. A stdio server should not use it; it should take credentials from the environment instead, such as environment variables set by the host.

- **Framework:** based on OAuth 2.1. The MCP server is an OAuth resource server, and a separate or co-located authorization server issues tokens. Clients send `Authorization: Bearer <token>` on every request.
- **Discovery:** the server must publish OAuth 2.0 Protected Resource Metadata (RFC 9728), pointed to by a `WWW-Authenticate` header on a 401 response or a well-known URI, to name its authorization servers. Clients then read Authorization Server Metadata (RFC 8414) or OpenID Connect Discovery.
- **Token binding:** clients must send the `resource` parameter from Resource Indicators (RFC 8707), and servers must reject tokens not issued for them. Token passthrough to upstream APIs is forbidden.
- **PKCE** is required for the authorization code flow.
- **Client registration:** in 2025-11-25, Client ID Metadata Documents became the recommended way for clients to identify themselves. Pre-registration and Dynamic Client Registration (RFC 7591) remain as alternatives.
- **Scopes:** servers can signal the scopes they need in `WWW-Authenticate` challenges, which allows step-up consent.

## What changed in recent revisions
- **2025-03-26:** Streamable HTTP replaced HTTP+SSE; the first OAuth 2.1 authorization framework; tool annotations.
- **2025-06-18:**
  - MCP servers classified as OAuth resource servers, with RFC 9728 metadata and RFC 8707 resource indicators required.
  - JSON-RPC batching removed.
  - `MCP-Protocol-Version` header required over HTTP.
  - Structured tool output and elicitation added.
- **2025-11-25:**
  - Client ID Metadata Documents for registration.
  - OpenID Connect Discovery support.
  - Incremental scope consent.
  - Experimental tasks for long-running requests.
  - Further refinements to elicitation and sampling.

## Recommendation for an internal tool
Offer stdio for local, single-user use: it is the simplest and credentials stay in the environment. For shared or remote access, use Streamable HTTP behind your identity provider, following the authorization spec: RFC 9728 metadata, audience-bound tokens and PKCE.

## Sources
- https://modelcontextprotocol.io/specification/2025-11-25/basic/transports
- https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization
- https://modelcontextprotocol.io/specification/2025-11-25/changelog
- https://modelcontextprotocol.io/specification/2025-06-18/changelog
- https://datatracker.ietf.org/doc/html/rfc9728
- https://datatracker.ietf.org/doc/html/rfc8707
