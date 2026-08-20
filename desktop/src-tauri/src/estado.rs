use crate::disk::DiskUsage;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Estado {
    Ok,
    Aviso,
    Critico,
}

const GB: u64 = 1024 * 1024 * 1024;

/// Classify disk pressure from both proportion and absolute free space.
///
/// Percentage alone is wrong at both ends of the drive-size range: 85% of a
/// 4 TB drive still leaves 600 GB, while 60% of a 128 GB drive leaves 51 GB,
/// which is already tight for Xcode and Docker. Red must mean "this is a
/// problem now" — if it shows up early, people stop looking at it.
pub fn classify(u: DiskUsage) -> Estado {
    let libre_gb = u.available / GB;
    if libre_gb < 25 || u.percent >= 95.0 {
        Estado::Critico
    } else if libre_gb < 75 || u.percent >= 85.0 {
        Estado::Aviso
    } else {
        Estado::Ok
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::disk::DiskUsage;

    fn uso(total_gb: u64, libre_gb: u64) -> DiskUsage {
        let gb = 1024u64 * 1024 * 1024;
        let total = total_gb * gb;
        let available = libre_gb * gb;
        let used = total - available;
        DiskUsage { total, used, available, percent: used as f64 / total as f64 * 100.0 }
    }

    #[test]
    fn disco_holgado_es_ok() {
        assert_eq!(classify(uso(500, 300)), Estado::Ok);
    }

    #[test]
    fn porcentaje_alto_pero_muchos_gb_libres_no_es_critico() {
        // 4 TB al 85%: 600 GB libres. No es urgente aunque el porcentaje asuste.
        assert_ne!(classify(uso(4000, 600)), Estado::Critico);
    }

    #[test]
    fn porcentaje_moderado_con_pocos_gb_si_avisa() {
        // 128 GB al 60%: 51 GB libres. Aprieta de verdad.
        assert_ne!(classify(uso(128, 51)), Estado::Ok);
    }

    #[test]
    fn el_caso_real_de_esta_maquina_es_critico() {
        // Medido al escribir el plan: 460 GB totales, 15.59 GB libres.
        assert_eq!(classify(uso(460, 15)), Estado::Critico);
    }
}
