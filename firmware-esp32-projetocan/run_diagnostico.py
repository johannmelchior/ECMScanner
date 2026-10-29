from pathlib import Path
from diagnostics.can_diagnostic_pipeline import analyze_folder


if __name__ == "__main__":
    base = Path(__file__).resolve().parent
    result = analyze_folder(
        log_dir=base / "logs" / "BRP-SEADOO-GTX-2022-300hp",
        odx_csv=base.parent / "docs" / "seadoo_odx_can_map.csv",
        out_dir=base.parent / "docs",
        profile_name="BRP_SEADOO_GTX_2022_300hp",
    )
    print("Analise concluida")
    for k, v in result.items():
        print(f"{k}: {v}")
