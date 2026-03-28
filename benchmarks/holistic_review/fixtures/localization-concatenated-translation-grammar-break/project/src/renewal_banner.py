from i18n import t


def build_renewal_banner(customer_name: str, renewal_date_label: str) -> str:
    return (
        t("billing.renewal_prefix")
        + customer_name
        + t("billing.renewal_middle")
        + renewal_date_label
        + t("billing.renewal_suffix")
    )