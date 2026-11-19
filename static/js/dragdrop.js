document.addEventListener('DOMContentLoaded', () => {
    function setup(dropArea, fileInput, callback) {
        if (!dropArea || !fileInput) return;

        fileInput.addEventListener("change", e => {
            const files = e.target.files;
            if (files && files.length > 0) callback(files);
        });

        ["dragenter", "dragover", "dragleave", "drop"].forEach(event =>
            dropArea.addEventListener(event, e => {
                e.preventDefault();
                e.stopPropagation();
            }, false)
        );

        ["dragenter", "dragover"].forEach(event =>
            dropArea.addEventListener(event, () => dropArea.classList.add("drag-over"), false)
        );

        ["dragleave", "drop"].forEach(event =>
            dropArea.addEventListener(event, () => dropArea.classList.remove("drag-over"), false)
        );

        dropArea.addEventListener("drop", e => {
            const files = e.dataTransfer.files;
            if (files && files.length > 0) callback(files);
        }, false);
    }

    window.setupDragDrop = function(areaId, inputId, cb) {
        setup(document.getElementById(areaId), document.getElementById(inputId), cb);
    };

    setup(
        document.getElementById("checker-drag-area"),
        document.getElementById("checker-file"),
        (files) => {
            const file = files[0];
            document.getElementById("checker-file-info").textContent = "Selected: " + file.name;
            const reader = new FileReader();
            reader.onload = e => {
                let lines = e.target.result.split(/\r?\n/).filter(x => x.trim());
                document.getElementById("checker-textarea").value = lines.join("\n");
                addLog("[Msk] Loaded " + lines.length + " tokens from file");
                toast.success("Tokens Loaded", lines.length + " tokens ready");
            };
            reader.readAsText(file);
        }
    );

    setup(
        document.getElementById("avatar-upload-area"),
        document.getElementById("avatar-upload-file"),
        async (files) => {
            const imageFiles = Array.from(files).filter(f => f.type.startsWith('image/'));
            if (imageFiles.length === 0) {
                toast.error("Error", "No valid image files found");
                return;
            }

            document.getElementById("avatar-upload-info").textContent = "Uploading " + imageFiles.length + " images...";

            for (const file of imageFiles) {
                try {
                    const reader = new FileReader();
                    const base64 = await new Promise((resolve, reject) => {
                        reader.onload = e => resolve(e.target.result);
                        reader.onerror = reject;
                        reader.readAsDataURL(file);
                    });

                    if (window.pywebview && window.pywebview.api) {
                        await window.pywebview.api.upload_avatar(file.name, base64);
                    }
                } catch (e) {
                    console.error("Failed to upload:", file.name, e);
                }
            }

            document.getElementById("avatar-upload-info").textContent = "Uploaded " + imageFiles.length + " images";
            toast.success("Upload Complete", imageFiles.length + " images added");
            await loadAvatarsFromBackend();
        }
    );
});
