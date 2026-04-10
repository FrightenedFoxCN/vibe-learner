import { ImageResponse } from "next/og";

export const size = {
  width: 180,
  height: 180
};

export const contentType = "image/png";

export default function AppleIcon() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "linear-gradient(160deg, #3f8c85, #8ed2c9)",
          color: "#fff7ee",
          fontSize: 76,
          fontWeight: 700
        }}
      >
        VL
      </div>
    ),
    size
  );
}
