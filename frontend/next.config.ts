import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      { source: "/api/:path*", destination: "http://127.0.0.1:5000/api/:path*" },
      { source: "/legacy/:path*", destination: "http://127.0.0.1:5000/:path*" },
      { source: "/calibrations/:path*/attachment", destination: "http://127.0.0.1:5000/calibrations/:path*/attachment" },
      { source: "/certs/:path*", destination: "http://127.0.0.1:5000/certs/:path*" },
    ];
  },
};

export default nextConfig;
