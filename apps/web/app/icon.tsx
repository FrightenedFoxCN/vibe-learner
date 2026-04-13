import { ImageResponse } from "next/og";

export const dynamic = "force-static";

export const size = {
  width: 64,
  height: 64
};

export const contentType = "image/png";

export default function Icon() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "linear-gradient(145deg, #c55c3b, #f2a56f)",
          color: "white",
          fontSize: 34,
          fontWeight: 700
        }}
      >
        VL
      </div>
    ),
    size
  );
}
