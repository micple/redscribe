/**
 * Redscribe Landing Page JavaScript
 * Handles animations, navigation, and interactive elements
 */

document.addEventListener('DOMContentLoaded', () => {
    // Initialize all components
    initScrollAnimations();
    initNavbar();
    initMobileMenu();
    initScreenshotSlider();
    initSmoothScroll();
});

/**
 * Scroll Animations using Intersection Observer
 */
function initScrollAnimations() {
    const animatedElements = document.querySelectorAll('.animate-on-scroll');

    const observerOptions = {
        root: null,
        rootMargin: '0px',
        threshold: 0.15
    };

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('visible');
                // Optionally unobserve after animation
                // observer.unobserve(entry.target);
            }
        });
    }, observerOptions);

    animatedElements.forEach(element => {
        observer.observe(element);
    });
}

/**
 * Navbar scroll effect
 */
function initNavbar() {
    const navbar = document.querySelector('.navbar');
    let lastScroll = 0;

    window.addEventListener('scroll', () => {
        const currentScroll = window.pageYOffset;

        // Add shadow on scroll
        if (currentScroll > 50) {
            navbar.classList.add('scrolled');
        } else {
            navbar.classList.remove('scrolled');
        }

        lastScroll = currentScroll;
    });
}

/**
 * Mobile menu toggle
 */
function initMobileMenu() {
    const navToggle = document.querySelector('.nav-toggle');
    const navLinks = document.querySelector('.nav-links');

    if (!navToggle || !navLinks) return;

    navToggle.addEventListener('click', () => {
        navLinks.classList.toggle('active');
        navToggle.classList.toggle('active');
    });

    // Close menu when clicking a link
    navLinks.querySelectorAll('a').forEach(link => {
        link.addEventListener('click', () => {
            navLinks.classList.remove('active');
            navToggle.classList.remove('active');
        });
    });

    // Close menu when clicking outside
    document.addEventListener('click', (e) => {
        if (!navToggle.contains(e.target) && !navLinks.contains(e.target)) {
            navLinks.classList.remove('active');
            navToggle.classList.remove('active');
        }
    });
}

/**
 * Screenshot slider
 */
function initScreenshotSlider() {
    const screenshots = document.querySelectorAll('.screenshot-item');
    const dots = document.querySelectorAll('.screenshot-dot');

    if (screenshots.length === 0 || dots.length === 0) return;

    let currentIndex = 0;
    let autoSlideInterval;

    function showSlide(index) {
        screenshots.forEach((screenshot, i) => {
            screenshot.classList.remove('active');
            dots[i].classList.remove('active');
        });

        screenshots[index].classList.add('active');
        dots[index].classList.add('active');
        currentIndex = index;
    }

    function nextSlide() {
        const next = (currentIndex + 1) % screenshots.length;
        showSlide(next);
    }

    // Click handlers for dots
    dots.forEach((dot, index) => {
        dot.addEventListener('click', () => {
            showSlide(index);
            resetAutoSlide();
        });
    });

    // Auto-slide every 5 seconds
    function startAutoSlide() {
        autoSlideInterval = setInterval(nextSlide, 5000);
    }

    function resetAutoSlide() {
        clearInterval(autoSlideInterval);
        startAutoSlide();
    }

    // Start auto-slide
    startAutoSlide();

    // Pause on hover
    const slider = document.querySelector('.screenshots-slider');
    if (slider) {
        slider.addEventListener('mouseenter', () => {
            clearInterval(autoSlideInterval);
        });

        slider.addEventListener('mouseleave', () => {
            startAutoSlide();
        });
    }
}

/**
 * Smooth scroll for anchor links
 */
function initSmoothScroll() {
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            e.preventDefault();

            const targetId = this.getAttribute('href');
            if (targetId === '#') return;

            const target = document.querySelector(targetId);
            if (!target) return;

            const navbarHeight = document.querySelector('.navbar').offsetHeight;
            const targetPosition = target.getBoundingClientRect().top + window.pageYOffset - navbarHeight;

            window.scrollTo({
                top: targetPosition,
                behavior: 'smooth'
            });
        });
    });
}

/**
 * Parallax effect for hero background (subtle)
 */
window.addEventListener('scroll', () => {
    const heroBackground = document.querySelector('.hero-background');
    if (!heroBackground) return;

    const scrolled = window.pageYOffset;
    const rate = scrolled * 0.3;

    heroBackground.style.transform = `translateY(${rate}px)`;
});

/**
 * Add loading animation
 */
window.addEventListener('load', () => {
    document.body.classList.add('loaded');
});
