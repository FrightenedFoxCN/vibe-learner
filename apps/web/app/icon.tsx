import { ImageResponse } from "next/og";
import { BrandMark, brandMarkStyle } from "../components/brand-mark";

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
          background: "transparent"
        }}
      >
        <BrandMark size={64} style={brandMarkStyle} />
      </div>
    ),
    size
  );
}
