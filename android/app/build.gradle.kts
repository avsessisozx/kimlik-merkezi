plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
}

// İmza YALNIZ ortam değişkenlerinden okunur (depoda anahtar/parola yok). Eksikse release İMZASIZ üretilir;
// debug anahtarına sessizce DÜŞÜLMEZ.
val imzaDosya: String? = System.getenv("KM_KEYSTORE_DOSYA")?.takeIf { it.isNotBlank() }
val imzaParola: String? = System.getenv("KM_KEYSTORE_PAROLA")?.takeIf { it.isNotEmpty() }
val imzaAd: String? = System.getenv("KM_ANAHTAR_AD")?.takeIf { it.isNotBlank() }
val imzaAnahtarParola: String? = System.getenv("KM_ANAHTAR_PAROLA")?.takeIf { it.isNotEmpty() }
val imzaVar = imzaDosya != null && imzaParola != null && imzaAd != null && imzaAnahtarParola != null && file(imzaDosya).exists()

android {
    namespace = "app.kimlikmerkezi.toplayici"
    compileSdk = 35

    defaultConfig {
        applicationId = "app.kimlikmerkezi.toplayici"
        minSdk = 30
        targetSdk = 35
        versionCode = 300
        versionName = "0.3.0"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    signingConfigs {
        if (imzaVar) {
            create("release") {
                storeFile = file(imzaDosya!!)
                storePassword = imzaParola
                keyAlias = imzaAd
                keyPassword = imzaAnahtarParola
            }
        }
    }
    buildTypes {
        release {
            // Bilinçli: R8 kuralları (Compose, kotlinx-serialization, WorkManager) doğrulanmadan küçültme yok.
            isMinifyEnabled = false
            // İmza değişkenleri yoksa signingConfig null kalır: çıktı app-release-unsigned.apk (debug imzasına düşmez).
            signingConfig = if (imzaVar) signingConfigs.getByName("release") else null
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
    buildFeatures {
        compose = true
        buildConfig = true
    }
    lint {
        abortOnError = true
        warningsAsErrors = false
    }
    sourceSets {
        // Sahte PC sunucusu ve yalnız-test anahtar deposu hem JVM hem emülatör testlerinde ortak.
        getByName("test") {
            java.srcDir("src/ortakTest/kotlin")
            resources.srcDir("src/ortakTest/resources")
        }
        getByName("androidTest") {
            java.srcDir("src/ortakTest/kotlin")
            resources.srcDir("src/ortakTest/resources")
        }
    }
    testOptions {
        unitTests.isReturnDefaultValues = true
    }
}

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.core.splashscreen)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.compose.ui)
    implementation(libs.androidx.compose.material3)
    implementation(libs.kotlinx.serialization.json)
    implementation(libs.androidx.exifinterface)
    implementation(libs.androidx.work.runtime)
    implementation(libs.androidx.camera.camera2)
    implementation(libs.androidx.camera.lifecycle)
    implementation(libs.androidx.camera.view)
    implementation(libs.zxing.core)
    implementation(libs.kotlinx.coroutines.android)

    testImplementation(libs.junit)
    testImplementation(libs.kotlin.test.junit)

    androidTestImplementation(platform(libs.androidx.compose.bom))
    androidTestImplementation(libs.androidx.test.ext.junit)
    androidTestImplementation(libs.androidx.test.runner)
    androidTestImplementation(libs.androidx.test.uiautomator)
    androidTestImplementation(libs.androidx.test.rules)
    androidTestImplementation(libs.androidx.compose.ui.test.junit4)
    debugImplementation(libs.androidx.compose.ui.test.manifest)
}
