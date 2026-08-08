/**
 * Plans selectable from the authenticated customer's own profile/dashboard
 * (Plans.tsx, Payment.tsx) -- NOT the captive portal, which fetches plans
 * unfiltered on its own. Static IP plans always require a technician, so
 * they're never self-service here. Hotspot plans are scoped to the
 * logged-in customer's own service_type: a PPPoE customer shouldn't see
 * Hotspot plans mixed into their list, but a Hotspot (or "both") customer
 * legitimately reaches this page too (e.g. via the MAC-capture flow in
 * Login/Register) and needs to see theirs. Guests (no logged-in user yet)
 * keep the old broad behavior since we don't know their intent.
 */
export function filterSelfServicePlans(plans: any[], userServiceType: string | undefined) {
    const nonStatic = plans.filter((p) => p.service_type !== 'static');
    if (!userServiceType || userServiceType === 'both') return nonStatic;
    return nonStatic.filter((p) => p.service_type === userServiceType);
}
