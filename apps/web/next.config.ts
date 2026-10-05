import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Keep the repository's maintained AGENTS.md as the instruction source.
  agentRules: false,
};

export default nextConfig;
