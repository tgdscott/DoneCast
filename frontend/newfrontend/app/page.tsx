import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Mic, Globe, Zap, Shield, Headphones, Radio, TrendingUp, Users, Sparkles, ArrowRight, Play } from "lucide-react"
import Link from "next/link"

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-background">
      {/* Navigation */}
      <nav className="border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 sticky top-0 z-50">
        <div className="container mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex h-16 items-center justify-between">
            <div className="flex items-center gap-2">
              <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-primary">
                <Radio className="w-6 h-6 text-primary-foreground" />
              </div>
              <span className="text-xl font-bold text-foreground">PodcastPlusPlus</span>
            </div>
            <div className="hidden md:flex items-center gap-8">
              <Link
                href="#features"
                className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
              >
                Features
              </Link>
              <Link
                href="#pricing"
                className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
              >
                Pricing
              </Link>
              <Link
                href="#about"
                className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
              >
                About
              </Link>
            </div>
            <div className="flex items-center gap-4">
              <Button variant="ghost" size="sm">
                Log In
              </Button>
              <Button size="sm" className="bg-primary text-primary-foreground hover:bg-primary/90">
                Start Free Trial
              </Button>
            </div>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="relative overflow-hidden bg-gradient-to-br from-primary/10 via-secondary/10 to-accent/10 py-20 sm:py-32">
        <div className="container mx-auto px-4 sm:px-6 lg:px-8">
          <div className="grid lg:grid-cols-2 gap-12 items-center">
            <div className="space-y-8">
              <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-primary/10 text-primary text-sm font-medium">
                <Sparkles className="w-4 h-4" />
                <span>Patent-Pending AI Technology</span>
              </div>
              <h1 className="text-5xl sm:text-6xl lg:text-7xl font-bold text-foreground leading-tight text-balance">
                Professional Podcasting
                <span className="text-primary"> For Everyone</span>
              </h1>
              <p className="text-xl text-muted-foreground leading-relaxed text-pretty max-w-2xl">
                No experience needed. No technical skills required. No age limit. Just you and your voice.
                PodcastPlusPlus makes professional podcasting so easy, it's faster and cheaper than hiring someone else
                to do it.
              </p>
              {/* ... existing code ... */}
              <div className="flex flex-col sm:flex-row gap-4">
                <Button size="lg" className="bg-primary text-primary-foreground hover:bg-primary/90 text-lg px-8 py-6">
                  Start Your Free Trial
                  <ArrowRight className="ml-2 w-5 h-5" />
                </Button>
                <Button size="lg" variant="outline" className="text-lg px-8 py-6 bg-transparent">
                  <Play className="mr-2 w-5 h-5" />
                  Watch Demo
                </Button>
              </div>
              <div className="flex items-center gap-8 pt-4">
                <div className="flex items-center gap-2">
                  <Sparkles className="w-5 h-5 text-primary" />
                  <span className="text-sm text-muted-foreground">Anyone can do this</span>
                </div>
                <div className="flex items-center gap-2">
                  <Zap className="w-5 h-5 text-accent" />
                  <span className="text-sm text-muted-foreground">Setup in 5 minutes</span>
                </div>
              </div>
            </div>
            <div className="relative">
              <div className="relative rounded-2xl overflow-hidden shadow-2xl">
                <img
                  src="/modern-podcast-recording-studio-with-professional-.jpg"
                  alt="Podcast Studio"
                  className="w-full h-auto"
                />
                <div className="absolute inset-0 bg-gradient-to-t from-primary/20 to-transparent" />
              </div>
              {/* Floating Stats Cards */}
              <Card className="absolute -bottom-6 -left-6 p-4 shadow-lg bg-card border-border">
                <div className="flex items-center gap-3">
                  <div className="w-12 h-12 rounded-lg bg-secondary/20 flex items-center justify-center">
                    <TrendingUp className="w-6 h-6 text-secondary" />
                  </div>
                  <div>
                    <div className="text-2xl font-bold text-card-foreground">Unlimited</div>
                    <div className="text-sm text-muted-foreground">Episodes & Storage</div>
                  </div>
                </div>
              </Card>
              <Card className="absolute -top-6 -right-6 p-4 shadow-lg bg-card border-border">
                <div className="flex items-center gap-3">
                  <div className="w-12 h-12 rounded-lg bg-accent/20 flex items-center justify-center">
                    <Globe className="w-6 h-6 text-accent" />
                  </div>
                  <div>
                    <div className="text-2xl font-bold text-card-foreground">Global</div>
                    <div className="text-sm text-muted-foreground">CDN Distribution</div>
                  </div>
                </div>
              </Card>
            </div>
          </div>
        </div>
      </section>

      <section className="py-20 sm:py-32 bg-gradient-to-br from-secondary/5 to-accent/5">
        <div className="container mx-auto px-4 sm:px-6 lg:px-8">
          <div className="grid lg:grid-cols-2 gap-12 items-center">
            <div className="relative order-2 lg:order-1">
              <div className="relative rounded-2xl overflow-hidden shadow-2xl">
                <img src="/ai-podcast-editing-interface.jpg" alt="AI Editing Interface" className="w-full h-auto" />
                <div className="absolute inset-0 bg-gradient-to-t from-secondary/30 to-transparent" />
              </div>
              <Card className="absolute -bottom-6 -right-6 p-6 shadow-lg bg-card border-border max-w-xs">
                <p className="text-lg font-semibold text-card-foreground mb-2">"This is the future of podcasting."</p>
                <p className="text-sm text-muted-foreground">What our beta testers are saying</p>
              </Card>
            </div>
            <div className="space-y-6 order-1 lg:order-2">
              <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-primary/10 text-primary text-sm font-medium">
                <Shield className="w-4 h-4" />
                <span>Patent Pending</span>
              </div>
              <h2 className="text-4xl sm:text-5xl font-bold text-foreground text-balance">
                Edit While You <span className="text-primary">Record</span>
              </h2>
              <p className="text-xl text-muted-foreground leading-relaxed text-pretty">
                Our revolutionary AI technology lets you edit your podcast in real-time as you're recording. Remove
                mistakes, add effects, and polish your content—all without stopping.
                <strong className="text-foreground"> Features you won't find anywhere else at any price.</strong>
              </p>
              <ul className="space-y-4">
                <li className="flex items-start gap-3">
                  <div className="w-6 h-6 rounded-full bg-primary/10 flex items-center justify-center flex-shrink-0 mt-1">
                    <Sparkles className="w-4 h-4 text-primary" />
                  </div>
                  <div>
                    <h4 className="font-semibold text-foreground mb-1">Instant Mistake Removal</h4>
                    <p className="text-muted-foreground">
                      Stumbled over words? Misspoke? AI finds and removes it in seconds—no stopping, no post-production
                      hassle.
                    </p>
                  </div>
                </li>
                <li className="flex items-start gap-3">
                  <div className="w-6 h-6 rounded-full bg-secondary/10 flex items-center justify-center flex-shrink-0 mt-1">
                    <Zap className="w-4 h-4 text-secondary" />
                  </div>
                  <div>
                    <h4 className="font-semibold text-foreground mb-1">Live AI "Intern"</h4>
                    <p className="text-muted-foreground">
                      Not sure about something? Ask your AI intern during recording and it instantly fact-checks for
                      your listeners.
                    </p>
                  </div>
                </li>
                <li className="flex items-start gap-3">
                  <div className="w-6 h-6 rounded-full bg-accent/10 flex items-center justify-center flex-shrink-0 mt-1">
                    <TrendingUp className="w-4 h-4 text-accent" />
                  </div>
                  <div>
                    <h4 className="font-semibold text-foreground mb-1">Voice-Activated Sound Effects</h4>
                    <p className="text-muted-foreground">
                      Want pro-quality sound effects? Just say "BOOM" and it's added live—no soundboard engineer needed.
                    </p>
                  </div>
                </li>
              </ul>
            </div>
          </div>
        </div>
      </section>

      <section className="py-20 sm:py-32">
        <div className="container mx-auto px-4 sm:px-6 lg:px-8">
          <div className="max-w-4xl mx-auto text-center mb-16">
            <h2 className="text-4xl sm:text-5xl font-bold text-foreground mb-6 text-balance">
              Done For You, <span className="text-primary">By You</span>
            </h2>
            <p className="text-xl text-muted-foreground text-pretty">
              Why pay someone else when you can do it yourself—faster, cheaper, and with complete creative control?
              PodcastPlusPlus is so intuitive that publishing your podcast takes less time and effort than explaining it
              to someone else.
            </p>
          </div>

          <div className="grid md:grid-cols-3 gap-8 mb-12">
            <Card className="p-8 text-center bg-card border-border">
              <div className="w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center mx-auto mb-6">
                <Zap className="w-8 h-8 text-primary" />
              </div>
              <h3 className="text-2xl font-bold text-card-foreground mb-3">Faster</h3>
              <p className="text-muted-foreground leading-relaxed">
                Record, edit, and publish in minutes. No back-and-forth with editors. No waiting days for revisions.
              </p>
            </Card>

            <Card className="p-8 text-center bg-card border-border">
              <div className="w-16 h-16 rounded-2xl bg-secondary/10 flex items-center justify-center mx-auto mb-6">
                <TrendingUp className="w-8 h-8 text-secondary" />
              </div>
              <h3 className="text-2xl font-bold text-card-foreground mb-3">Cheaper</h3>
              <p className="text-muted-foreground leading-relaxed">
                One affordable subscription replaces expensive editors, hosting fees, and distribution services.
              </p>
            </Card>

            <Card className="p-8 text-center bg-card border-border">
              <div className="w-16 h-16 rounded-2xl bg-accent/10 flex items-center justify-center mx-auto mb-6">
                <Sparkles className="w-8 h-8 text-accent" />
              </div>
              <h3 className="text-2xl font-bold text-card-foreground mb-3">Easier</h3>
              <p className="text-muted-foreground leading-relaxed">
                So simple, your grandparents could use it. So powerful, professionals choose it. That's the magic.
              </p>
            </Card>
          </div>

          <div className="relative rounded-2xl overflow-hidden shadow-2xl">
            <img src="/podcast-creator-workflow.jpg" alt="Simple Podcast Workflow" className="w-full h-auto" />
            <div className="absolute inset-0 bg-gradient-to-t from-background/80 to-transparent flex items-end">
              <div className="p-8 sm:p-12">
                <h3 className="text-2xl sm:text-3xl font-bold text-foreground mb-2">
                  Your Voice. Your Vision. Your Control.
                </h3>
                <p className="text-lg text-muted-foreground">
                  No middleman. No compromises. Just pure creative freedom.
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="py-20 sm:py-32 bg-gradient-to-br from-primary/5 to-secondary/5">
        <div className="container mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-16">
            <h2 className="text-4xl sm:text-5xl font-bold text-foreground mb-4 text-balance">
              From Idea to Published in <span className="text-primary">3 Simple Steps</span>
            </h2>
            <p className="text-xl text-muted-foreground max-w-2xl mx-auto text-pretty">
              Seriously, it's this easy. No technical knowledge required. No learning curve. Just start talking.
            </p>
          </div>

          <div className="grid md:grid-cols-3 gap-8 max-w-5xl mx-auto">
            <div className="relative">
              <div className="text-center">
                <div className="w-20 h-20 rounded-2xl bg-primary/10 flex items-center justify-center mx-auto mb-6 border-4 border-primary/20">
                  <span className="text-4xl font-bold text-primary">1</span>
                </div>
                <h3 className="text-2xl font-bold text-foreground mb-3">Record</h3>
                <p className="text-muted-foreground leading-relaxed">
                  Hit record and start talking. Our AI handles the rest—removing mistakes, enhancing audio, and creating
                  chapters.
                </p>
              </div>
              <div className="hidden md:block absolute top-10 -right-4 w-8 h-0.5 bg-gradient-to-r from-primary to-secondary" />
            </div>

            <div className="relative">
              <div className="text-center">
                <div className="w-20 h-20 rounded-2xl bg-secondary/10 flex items-center justify-center mx-auto mb-6 border-4 border-secondary/20">
                  <span className="text-4xl font-bold text-secondary">2</span>
                </div>
                <h3 className="text-2xl font-bold text-foreground mb-3">Review</h3>
                <p className="text-muted-foreground leading-relaxed">
                  Preview your episode with AI-applied edits. Make any final tweaks with our simple, intuitive editor.
                </p>
              </div>
              <div className="hidden md:block absolute top-10 -right-4 w-8 h-0.5 bg-gradient-to-r from-secondary to-accent" />
            </div>

            <div className="text-center">
              <div className="w-20 h-20 rounded-2xl bg-accent/10 flex items-center justify-center mx-auto mb-6 border-4 border-accent/20">
                <span className="text-4xl font-bold text-accent">3</span>
              </div>
              <h3 className="text-2xl font-bold text-foreground mb-3">Publish</h3>
              <p className="text-muted-foreground leading-relaxed">
                One click distributes your podcast to Spotify, Apple Podcasts, and 20+ platforms. You're live!
              </p>
            </div>
          </div>

          <div className="text-center mt-12">
            <Button size="lg" className="bg-primary text-primary-foreground hover:bg-primary/90 text-lg px-8 py-6">
              Start Your First Episode Now
              <ArrowRight className="ml-2 w-5 h-5" />
            </Button>
          </div>
        </div>
      </section>

      {/* Features Grid */}
      <section id="features" className="py-20 sm:py-32">
        <div className="container mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-16">
            <h2 className="text-4xl sm:text-5xl font-bold text-foreground mb-4 text-balance">
              Everything You Need to <span className="text-primary">Succeed</span>
            </h2>
            <p className="text-xl text-muted-foreground max-w-2xl mx-auto text-pretty">
              Professional-grade tools that would normally cost thousands. All included in one simple platform.
            </p>
          </div>

          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-8">
            {/* Feature 1 */}
            <Card className="p-8 hover:shadow-lg transition-shadow bg-card border-border">
              <div className="w-14 h-14 rounded-xl bg-primary/10 flex items-center justify-center mb-6">
                <Mic className="w-7 h-7 text-primary" />
              </div>
              <h3 className="text-2xl font-bold text-card-foreground mb-3">Unlimited Hosting</h3>
              <p className="text-muted-foreground leading-relaxed">
                Upload unlimited episodes with no storage limits. Your content, your way, without restrictions.
              </p>
            </Card>

            {/* Feature 2 */}
            <Card className="p-8 hover:shadow-lg transition-shadow bg-card border-border">
              <div className="w-14 h-14 rounded-xl bg-secondary/10 flex items-center justify-center mb-6">
                <Sparkles className="w-7 h-7 text-secondary" />
              </div>
              <h3 className="text-2xl font-bold text-card-foreground mb-3">AI-Powered Editing</h3>
              <p className="text-muted-foreground leading-relaxed">
                Edit while you record with patent-pending AI that removes mistakes, adds effects, and polishes your
                audio in real-time.
              </p>
            </Card>

            {/* Feature 3 */}
            <Card className="p-8 hover:shadow-lg transition-shadow bg-card border-border">
              <div className="w-14 h-14 rounded-xl bg-accent/10 flex items-center justify-center mb-6">
                <Globe className="w-7 h-7 text-accent" />
              </div>
              <h3 className="text-2xl font-bold text-card-foreground mb-3">Global Distribution</h3>
              <p className="text-muted-foreground leading-relaxed">
                Automatically distribute to Spotify, Apple Podcasts, Google Podcasts, and 20+ platforms.
              </p>
            </Card>

            {/* Feature 4 */}
            <Card className="p-8 hover:shadow-lg transition-shadow bg-card border-border">
              <div className="w-14 h-14 rounded-xl bg-primary/10 flex items-center justify-center mb-6">
                <Zap className="w-7 h-7 text-primary" />
              </div>
              <h3 className="text-2xl font-bold text-card-foreground mb-3">Lightning Fast</h3>
              <p className="text-muted-foreground leading-relaxed">
                Global CDN ensures your episodes load instantly for listeners anywhere in the world.
              </p>
            </Card>

            {/* Feature 5 */}
            <Card className="p-8 hover:shadow-lg transition-shadow bg-card border-border">
              <div className="w-14 h-14 rounded-xl bg-secondary/10 flex items-center justify-center mb-6">
                <Users className="w-7 h-7 text-secondary" />
              </div>
              <h3 className="text-2xl font-bold text-card-foreground mb-3">Team Collaboration</h3>
              <p className="text-muted-foreground leading-relaxed">
                Invite team members, manage permissions, and collaborate seamlessly on your podcast.
              </p>
            </Card>

            {/* Feature 6 */}
            <Card className="p-8 hover:shadow-lg transition-shadow bg-card border-border">
              <div className="w-14 h-14 rounded-xl bg-accent/10 flex items-center justify-center mb-6">
                <Headphones className="w-7 h-7 text-accent" />
              </div>
              <h3 className="text-2xl font-bold text-card-foreground mb-3">Custom Player</h3>
              <p className="text-muted-foreground leading-relaxed">
                Beautiful, embeddable podcast player that matches your brand and engages listeners.
              </p>
            </Card>
          </div>
        </div>
      </section>

      <section className="py-20 sm:py-32 bg-gradient-to-br from-accent/5 to-primary/5">
        <div className="container mx-auto px-4 sm:px-6 lg:px-8">
          <div className="grid lg:grid-cols-2 gap-12 items-center">
            <div className="space-y-6">
              <h2 className="text-4xl sm:text-5xl font-bold text-foreground text-balance">
                Why <span className="text-primary">PodcastPlusPlus</span>?
              </h2>
              <p className="text-xl text-muted-foreground leading-relaxed text-pretty">
                We've built something truly special here. Technology that doesn't exist anywhere else. A platform that
                makes the impossible feel effortless. This is podcasting, reimagined.
              </p>

              <div className="space-y-6 pt-4">
                <div className="flex items-start gap-4">
                  <div className="w-12 h-12 rounded-xl bg-primary/10 flex items-center justify-center flex-shrink-0">
                    <Shield className="w-6 h-6 text-primary" />
                  </div>
                  <div>
                    <h4 className="text-lg font-semibold text-foreground mb-2">Patent-Pending Innovation</h4>
                    <p className="text-muted-foreground">
                      Technology you literally can't get anywhere else. We invented it.
                    </p>
                  </div>
                </div>

                <div className="flex items-start gap-4">
                  <div className="w-12 h-12 rounded-xl bg-secondary/10 flex items-center justify-center flex-shrink-0">
                    <Users className="w-6 h-6 text-secondary" />
                  </div>
                  <div>
                    <h4 className="text-lg font-semibold text-foreground mb-2">Built For Everyone</h4>
                    <p className="text-muted-foreground">
                      From first-timers to seasoned pros. From teens to retirees. Anyone can create here.
                    </p>
                  </div>
                </div>

                <div className="flex items-start gap-4">
                  <div className="w-12 h-12 rounded-xl bg-accent/10 flex items-center justify-center flex-shrink-0">
                    <TrendingUp className="w-6 h-6 text-accent" />
                  </div>
                  <div>
                    <h4 className="text-lg font-semibold text-foreground mb-2">Unbeatable Value</h4>
                    <p className="text-muted-foreground">
                      Replace your editor, hosting, and distribution services with one affordable platform.
                    </p>
                  </div>
                </div>

                <div className="flex items-start gap-4">
                  <div className="w-12 h-12 rounded-xl bg-primary/10 flex items-center justify-center flex-shrink-0">
                    <Sparkles className="w-6 h-6 text-primary" />
                  </div>
                  <div>
                    <h4 className="text-lg font-semibold text-foreground mb-2">AI That Actually Works</h4>
                    <p className="text-muted-foreground">
                      Not gimmicky features. Real AI that saves you hours and makes you sound professional.
                    </p>
                  </div>
                </div>
              </div>
            </div>

            <div className="relative">
              <div className="relative rounded-2xl overflow-hidden shadow-2xl">
                <img src="/podcast-success-dashboard.jpg" alt="Success Dashboard" className="w-full h-auto" />
                <div className="absolute inset-0 bg-gradient-to-t from-primary/20 to-transparent" />
              </div>
              <Card className="absolute -bottom-6 -left-6 p-6 shadow-lg bg-card border-border max-w-xs">
                <p className="text-lg font-semibold text-card-foreground mb-2">"This is the future of podcasting."</p>
                <p className="text-sm text-muted-foreground">What our beta testers are saying</p>
              </Card>
            </div>
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="py-20 sm:py-32 bg-gradient-to-br from-primary via-secondary to-accent relative overflow-hidden">
        <div className="absolute inset-0 bg-[url('/abstract-podcast-waveform-pattern.jpg')] opacity-10 bg-cover bg-center" />
        <div className="container mx-auto px-4 sm:px-6 lg:px-8 relative z-10">
          <div className="max-w-4xl mx-auto text-center">
            <h2 className="text-4xl sm:text-5xl lg:text-6xl font-bold text-primary-foreground mb-6 text-balance">
              Ready to Take Your Podcast to the Next Level?
            </h2>
            <p className="text-xl text-primary-foreground/90 mb-10 text-pretty">
              Join the next generation of podcasters who are building their audience with PodcastPlusPlus
            </p>
            <div className="flex flex-col sm:flex-row gap-4 justify-center">
              <Button
                size="lg"
                variant="secondary"
                className="text-lg px-8 py-6 bg-background text-foreground hover:bg-background/90"
              >
                Start Your Free Trial
                <ArrowRight className="ml-2 w-5 h-5" />
              </Button>
              <Button
                size="lg"
                variant="outline"
                className="text-lg px-8 py-6 border-primary-foreground text-primary-foreground hover:bg-primary-foreground/10 bg-transparent"
              >
                Schedule a Demo
              </Button>
            </div>
            <p className="text-sm text-primary-foreground/80 mt-6">
              14-day free trial • No credit card required • Cancel anytime
            </p>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="bg-muted py-12 border-t border-border">
        <div className="container mx-auto px-4 sm:px-6 lg:px-8">
          <div className="grid md:grid-cols-4 gap-8 mb-8">
            <div>
              <div className="flex items-center gap-2 mb-4">
                <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-primary">
                  <Radio className="w-5 h-5 text-primary-foreground" />
                </div>
                <span className="text-lg font-bold text-foreground">PodcastPlusPlus</span>
              </div>
              <p className="text-sm text-muted-foreground">Professional podcast hosting for the modern creator.</p>
            </div>
            <div>
              <h4 className="font-semibold text-foreground mb-4">Product</h4>
              <ul className="space-y-2 text-sm text-muted-foreground">
                <li>
                  <Link href="#" className="hover:text-foreground transition-colors">
                    Features
                  </Link>
                </li>
                <li>
                  <Link href="#" className="hover:text-foreground transition-colors">
                    Pricing
                  </Link>
                </li>
                <li>
                  <Link href="#" className="hover:text-foreground transition-colors">
                    FAQ
                  </Link>
                </li>
              </ul>
            </div>
            <div>
              <h4 className="font-semibold text-foreground mb-4">Company</h4>
              <ul className="space-y-2 text-sm text-muted-foreground">
                <li>
                  <Link href="#" className="hover:text-foreground transition-colors">
                    About
                  </Link>
                </li>
                <li>
                  <Link href="#" className="hover:text-foreground transition-colors">
                    Blog
                  </Link>
                </li>
                <li>
                  <Link href="#" className="hover:text-foreground transition-colors">
                    Contact
                  </Link>
                </li>
              </ul>
            </div>
            <div>
              <h4 className="font-semibold text-foreground mb-4">Legal</h4>
              <ul className="space-y-2 text-sm text-muted-foreground">
                <li>
                  <Link href="#" className="hover:text-foreground transition-colors">
                    Privacy
                  </Link>
                </li>
                <li>
                  <Link href="#" className="hover:text-foreground transition-colors">
                    Terms
                  </Link>
                </li>
              </ul>
            </div>
          </div>
          <div className="pt-8 border-t border-border text-center text-sm text-muted-foreground">
            <p>&copy; 2025 PodcastPlusPlus. All rights reserved.</p>
          </div>
        </div>
      </footer>
    </div>
  )
}
