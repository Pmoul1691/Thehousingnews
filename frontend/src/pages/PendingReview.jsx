import React from "react";

export default function PendingReview() {
  return (
    <div className="container-prose py-24 text-center animate-fade-up">
      <p className="uppercase-label mb-3">Request received</p>
      <h1 className="font-display font-semibold text-3xl sm:text-4xl ink mb-6">We will read it shortly.</h1>
      <p className="font-serif text-lg leading-relaxed text-[#2C2410]/80 max-w-prose mx-auto">
        We read every note personally. You will hear back from us within 48 hours, by email.
      </p>
      <p className="font-serif text-base mt-6 text-muted-ink">The Editors</p>
    </div>
  );
}
