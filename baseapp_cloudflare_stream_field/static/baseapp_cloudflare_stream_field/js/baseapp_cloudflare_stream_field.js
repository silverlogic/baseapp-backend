// Check that the djangoAdminResumableFieldListenerSetUp variable exist.
if (typeof djangoAdminCloudflareStreamFieldListenerSetUp == "undefined") {
  var djangoAdminCloudflareStreamFieldListenerSetUp = false;
}

addEventListener("load", function() {
  (function($) {
       $('input.baseapp_cloudflare_stream_field-input-file').on('change', function(e) {
          var fileFied = $(this)
          var strippedId = fileFied.attr('id').replace('_input_file', '')
          var videoIdField = $('#' + strippedId)
          var progressField = $('#' + strippedId + '_progress')
          var statusField = $("#" + strippedId + "_uploaded_status")

          var file = e.target.files[0]

          // Create a new tus upload
          var upload = new tus.Upload(file, {
              endpoint: "/cloudflare-stream-upload/",
              retryDelays: [0, 3000, 5000, 10000, 20000],
              chunkSize: 50 * 1024 * 1024,  // 5MB
              metadata: {
                  filename: file.name,
                  filetype: file.type
              },
              onBeforeRequest: function(req) {
                  statusField.html('⏳ Uploading... ')
              },
              onError: function(error) {
                  console.error("Failed because: ", error)
                  statusField.html('❌ Error while uploading - please re-upload this file')
              },
              onProgress: function(bytesUploaded, bytesTotal) {
                  var percentage = (bytesUploaded / bytesTotal * 100).toFixed(2)
                  progressField.val(percentage)
              },
              onSuccess: function() {
                  var uploadUrl = new URL(upload.url)
                  var videoId = uploadUrl.pathname.split("/").pop()
                  videoIdField.val(videoId)
                  statusField.html('✅ Uploaded');
              }
          })

          // Check if there are any previous uploads to continue.
          upload.findPreviousUploads().then(function (previousUploads) {
              // Found previous uploads so we select the first one. 
              if (previousUploads.length) {
                  upload.resumeFromPreviousUpload(previousUploads[0])
              }

              // Start the upload
              upload.start()
          })
      });
  })(typeof django !== "undefined" ? django.jQuery : jQuery);
});
