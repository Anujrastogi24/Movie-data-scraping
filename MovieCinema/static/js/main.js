// Swiper 
var swiper = new Swiper(".popular-content", {
    slidesPerView: 1,
    spaceBetween: 10,
    autoplay: {
      delay: 5500,
      disableOnInteraction: false,
    },
    pagination: {
      el: ".swiper-pagination",
      clickable: true,
    },
    navigation: {
      nextEl: ".swiper-button-next",
      prevEl: ".swiper-button-prev",
    },
    breakpoints: {
        280:{
            slidesPerView: 1,
            spaceBetween: 10,

        },
        320:{
            slidesPerView: 2,
            spaceBetween: 10,
        },
        510:{
            slidesPerView: 3,
            spaceBetween: 15,
        },
        900:{
            slidesPerView: 4,
            spaceBetween: 20,
        },

    },
  });
  // Show Video
  let playButton = document.querySelector('.watch-btn');
  let video = document.querySelector(".video-container");
  let myvideo = document.querySelector("#myvideo");
  let closebtn = document.querySelector('.close-video');
  

  playButton.onclick = () => {
    video.classList.add("show-video");
    // Auto play When Click on Button
    myvideo.play();
  };
  closebtn.onclick = () => {
    video.classList.remove("show-video");
    // Pause On Close Video
    myvideo.pause();
  };

  function setPlaySrc(link){ 
    let url = link.dataset.url;
    document.getElementById("myvideo").src = url; 
  }


 // setup the video element and attach it to the Dash player
//  function setupVideo() {
//   var url = "";
//   var context = new Dash.di.DashContext();
//   var player = new MediaPlayer(context);
//                   player.startup();
//                   player.attachView(document.querySelector('#myvideo'));
//                   player.attachSource(url);
// };
     

//  var iframe = document.querySelector('#myvideo');
//  iframe.setAttribute('src', ''); 
// const links = ['http://sv3.hivamovie.com/new/Movie/Gerry.2002/Gerry.2002.Trailer.mp4', 'http://sv3.hivamovie.com/new/Movie/City.of.God.2002/City.of.God.2002.mp4', 'http://sv3.hivamovie.com/new/Movie/Catch.Me.If.You.Can.2002/Catch.Me.If.You.Can.2002.mp4']

// const videoElements = links.map((url) => {
//   const videoElement = document.querySelector('#myvideo');
//   videoElement.addSource = url;
//   return videoElement;
// });
